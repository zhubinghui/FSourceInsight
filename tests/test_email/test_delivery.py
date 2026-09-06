import pytest

from app.email.digest import build_daily_digest
from app.email.sender import send_digest_email, send_keyword_alert
from app.extensions import mail
from app.models.article import Article
from app.models.email_log import EmailLog
from app.models.source import NewsSource


@pytest.fixture
def article(db):
    source = NewsSource(name='Synthetic', slug='synthetic', url='https://test.invalid', category='national')
    db.session.add(source)
    db.session.flush()
    item = Article(source_id=source.id, url='https://test.invalid/news', title_fr='Highlighted research',
                   summary_fr='Synthetic summary', highlights=['local_research'])
    db.session.add(item)
    db.session.commit()
    return item


def test_highlight_only_digest_sent_and_previewed(app, client, db, users, login, article, monkeypatch):
    sent = []
    monkeypatch.setattr(mail, 'send', sent.append)
    data = build_daily_digest(users['admin'])
    assert data['article_count'] == 1 and data['articles'] == []
    send_digest_email(users['admin'], data)
    assert len(sent) == 1
    assert 'Highlighted research' in sent[0].html
    assert 'Top Insights' in sent[0].html
    assert sent[0].recipients == ['admin@test.invalid']
    log = EmailLog.query.one()
    assert log.status == 'sent' and log.article_count == 1
    login('admin')
    preview = client.get('/admin/email-preview')
    assert preview.status_code == 200
    assert 'Highlighted research' in preview.text and 'Top Insights' in preview.text


def test_keyword_alert_uses_real_template_and_records_smtp_failure(db, users, monkeypatch):
    def failed_send(message):
        assert 'Quantum optics' in message.html
        raise OSError('simulated SMTP unavailable')

    monkeypatch.setattr(mail, 'send', failed_send)
    matches = [{'title': 'Quantum optics', 'url': 'https://test.invalid/news', 'keyword': 'quantum',
                'source': 'Synthetic', 'summary': '', 'published_at': None}]
    with pytest.raises(OSError, match='simulated SMTP'):
        send_keyword_alert(users['owner'], matches)
    log = EmailLog.query.one()
    assert log.status == 'failed'
    assert 'simulated SMTP' in log.error_message
