"""One configured order for the client and Admin routing matrix."""
TASK_TYPES = ['translate', 'digest', 'summarize', 'ner', 'sentiment', 'classify', 'insight', 'company_analysis']


def ordered_configs(configs, task):
    configs = [c for c in configs if c.is_active and c.role in ('primary', 'fallback')]
    assigned = [c for c in configs if task in (c.tasks or [])]
    # Existing databases routed company analysis through insight. Retain that
    # compatibility only when no explicit company_analysis assignment exists.
    if task == 'company_analysis' and not assigned:
        assigned = [c for c in configs if 'insight' in (c.tasks or [])]
    defaults = [c for c in configs if c.is_default and c not in assigned]

    def order(config):
        cost = float(config.cost_per_1k_input) if config.cost_per_1k_input is not None else float('inf')
        return (config.role != 'primary', config.priority, cost, config.id)
    return sorted(assigned, key=order) + sorted(defaults, key=order)
