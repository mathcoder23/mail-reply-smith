import yaml
from loguru import logger
import time
import argparse

from email_poller import EmailPoller


def load_config(path="./config/config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Mail Reply Smith: An automated email processing tool.")
    parser.add_argument(
        "-c", "--config",
        default="./config/config.yaml",
        help="Path to the configuration file."
    )
    args = parser.parse_args()

    config = load_config(args.config)
    logger.info(f"Configuration loaded successfully from {args.config}.")
    logger.debug(f"Loaded configuration:\n{yaml.dump(config, indent=2, allow_unicode=True, sort_keys=False)}")
    poller = EmailPoller(config)
    poller.start()
    
    try:
        # Keep the main thread alive to allow the background thread to run
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutdown signal received.")
    finally:
        poller.stop()
        logger.info("Application has shut down gracefully.")

if __name__ == "__main__":
    logger.add("logs/app.log", rotation="10 MB")
    main()
