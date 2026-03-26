def pagination_range(page, total_pages, window=2):
    """Generate a range of page numbers for pagination UI."""
    start = max(1, page - window)
    end = min(total_pages, page + window)
    return range(start, end + 1)
