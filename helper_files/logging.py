import logging

def get_logger(level = logging.INFO, log_file_name = 'system.log'):
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_file_name),  # Log messages to a file
        ]
    )

    console_logger = logging.getLogger('console')

    if not console_logger.handlers:
        console_logger.setLevel(level)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter('%(message)s')  # Simplified format for console
        console_handler.setFormatter(console_formatter)
        console_logger.addHandler(console_handler)
        console_logger.propagate = False  # Prevent double logging

    return console_logger