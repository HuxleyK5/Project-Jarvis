"""Keep search terms, OAuth data and bearer headers out of routine application logs."""

import logging


class GoogleAccessFilter(logging.Filter):
    def filter(self, record):
        # Uvicorn's access record is (client, method, full_path, version, status).
        if isinstance(record.args, tuple) and len(record.args) == 5:
            values = list(record.args)
            if str(values[2]).startswith('/integrations/google'):
                values[2] = '/integrations/google/[redacted]'
                record.args = tuple(values)
        return True


class GoogleHTTPFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return not any(host in message for host in ('.googleapis.com', 'accounts.google.com', 'www.googleapis.com'))


def install_log_privacy():
    for name, filter_type in [('uvicorn.access', GoogleAccessFilter), ('httpx', GoogleHTTPFilter)]:
        logger = logging.getLogger(name)
        if not any(isinstance(item, filter_type) for item in logger.filters):
            logger.addFilter(filter_type())
    # httpcore DEBUG traces can include authorization headers; never enable them here.
    logging.getLogger('httpcore').setLevel(logging.WARNING)
