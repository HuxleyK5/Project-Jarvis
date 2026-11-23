"""Verify observable tool contracts without asking the model to judge its own actions."""


def verify(tool, result):
    if not isinstance(result, dict):
        return False, 'Tool returned no structured result.'
    if tool == 'system_info':
        valid = isinstance(result.get('os'), str) and type(result.get('workspace_disk_total_bytes')) is int and result['workspace_disk_total_bytes'] > 0
        return valid, 'System information returned; unknown hardware fields remain unknown.'
    if tool in {'list_directory', 'search_files'}:
        valid = (isinstance(result.get('entries'), list) and type(result.get('truncated')) is bool
                 and all(isinstance(item, dict) and isinstance(item.get('path'), str)
                         and item.get('kind') in {'file', 'directory'} for item in result['entries']))
        return valid, 'Bounded file enumeration returned; results may be truncated.' if result.get('truncated') else 'File enumeration returned; an empty match list is valid.'
    if tool == 'read_text':
        valid = (isinstance(result.get('text'), str) and result.get('untrusted_document') is True
                 and type(result.get('characters')) is int and result['characters'] == len(result['text']))
        return valid, 'Selected document read locally; its claims are not independently verified.'
    if tool in {'open_application', 'open_website'}:
        valid = result.get('message') == 'Open request accepted by Windows. Window or page loading is not verified.'
        return valid, 'Windows launch handoff acknowledged. Visible window/page state is unverified.'
    return False, 'No verifier exists for this tool.'
