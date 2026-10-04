"""Apply the saved Case output policy without changing legacy result coverage."""


def selected_output_times(times, config):
    policy = config.get('_studio', {}).get('termination', {})
    if policy.get('include_initial') is False:
        return [value for value in times if float(value) != 0]
    return list(times)
