import email
import imaplib
import smtplib
import threading
import time
from email.message import EmailMessage
from email.utils import parseaddr, formataddr

from loguru import logger


class EmailPoller:
    """
    A class to poll for new emails in a separate thread at a specified interval.
    """

    def __init__(self, config):
        self.config = config
        self.running = False
        self.thread = None
        self.fetch_interval = self.config['pull_email']['fetch_interval_seconds']

    def _poll_loop(self):
        """The main polling loop that runs in a separate thread."""
        logger.info(f"Email poller thread started. Checking for new emails every {self.fetch_interval} seconds.")
        while self.running:
            try:
                self.fetch_emails()
                # Use a loop with a shorter sleep to be more responsive to the stop signal
                for _ in range(self.fetch_interval):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                logger.error(f"An error occurred during email polling: {e}")
                # Prevent rapid-fire failures by waiting before retrying
                time.sleep(60)

    def fetch_emails(self):
        """Fetches emails and applies filters based on the configuration."""
        transport_type = self.config['pull_email']['transport']
        if transport_type.lower() != 'imap':
            logger.warning(f"Transport type '{transport_type}' not implemented yet.")
            return

        logger.info(f"Fetching emails using {transport_type}...")

        transport_config = self.config['transport_config']['imap']
        smtp_config = self.config['transport_config']['smtp']
        filters = self.config.get('filters', [])
        folder = self.config['pull_email']['select_folder']
        keep_unseen_count = self.config['pull_email'].get('keep_unseen_count', 100)

        mail, emails = self.fetch_unseen_emails(
            host=transport_config['host'],
            port=transport_config.get('port', 993),
            user=transport_config['user'],
            password=transport_config['password'],
            folder=folder,
            is_fix_163provider_issue=transport_config.get('is_fix_163provider_issue', False)
        )

        if not mail:
            logger.warning("IMAP connection failed, skipping email processing.")
            return

        try:
            if not emails:
                logger.debug("No new emails to process.")
                return

            logger.info(f"Processing {len(emails)} new email(s)...")
            forward_acked_count = 0
            force_acked_count = 0
            for num, msg in emails:
                subject = self.sanitize_header(msg.get("Subject", "No Subject"))
                is_processed = False
                for rule in filters:
                    if self._match_rule(msg, rule):
                        logger.info(f"Email ID {num.decode()} (Subject: '{subject}') matched rule: {rule}. Executing action.")
                        self._execute_action(msg, rule, mail, num, smtp_config)
                        # Stop processing other rules for this email
                        is_processed = True
                        forward_acked_count += 1
                        break
                if not is_processed:
                    # This logic prevents the inbox from filling up. It marks all but the last non-matching email as "Seen".
                    remaining_emails = len(emails) - (forward_acked_count + force_acked_count)
                    if remaining_emails > keep_unseen_count:
                        logger.info(f"Force-acknowledging email ID {num.decode()} (Subject: '{subject}') to clear queue (did not match any rule).")
                        self.ack_email(mail, num, msg)
                        force_acked_count += 1
        finally:
            if mail:
                mail.close()
                mail.logout()
                logger.debug("IMAP connection closed.")

        logger.success("Finished processing emails. Waiting for next interval.")

    def _match_rule(self, msg, rule):
        """Check if an email message matches a given filter rule."""
        subject = self.sanitize_header(msg.get("Subject", "No Subject"))
        original_sender_name, original_sender_email = parseaddr(msg.get("From", ""))
        if 'sender_email_contains' in rule:
            if any(condition in original_sender_email for condition in rule['sender_email_contains']):
                return True
        return False

    def _execute_action(self, msg, rule, mail, num, smtp_config):
        """Execute the action defined in a rule for a given email."""
        action = rule.get('action')
        if action == 'forward':
            forward_to = rule.get('forward_to')
            if forward_to:
                try:
                    self.forward_email(msg, smtp_config, forward_to)
                    self.ack_email(mail, num, msg)
                except Exception as e:
                    subject = self.sanitize_header(msg.get("Subject", "No Subject"))
                    logger.error(f"Failed to execute forward action for email ID {num.decode()} (Subject: '{subject}'): {e}")
            else:
                logger.warning(f"Forward action for rule {rule} has no 'forward_to' address.")
        else:
            logger.warning(f"Action '{action}' in rule {rule} is not implemented.")

    def fetch_unseen_emails(self, host, port, user, password, folder, is_fix_163provider_issue):
        """
        Fetch unseen emails from IMAP folder.
        Returns a tuple: (mail, [(num, EmailMessage), ...])
        The caller is responsible for acking (marking as seen) or closing the connection.
        """
        try:
            mail = imaplib.IMAP4_SSL(host, port)
            mail.login(user, password)

            if is_fix_163provider_issue:
                # Fix for "Unsafe Login" (NetEase/188 email issue)
                try:
                    imaplib.Commands["ID"] = ('AUTH',)
                    args = ("name", user, "contact", password, "version", "1.0.0", "vendor", "myclient")
                    mail._simple_command("ID", str(args).replace(",", "").replace("'", "\""))
                except Exception as e:
                    logger.debug(f"IMAP ID command skipped or failed: {e}")

            mail.select(folder)
            result, data = mail.search(None, 'UNSEEN')
            if result != 'OK':
                logger.debug("No unseen messages found.")
                return mail, []

            email_list = []
            for num in data[0].split():
                result, msg_data = mail.fetch(num, '(BODY.PEEK[])')
                if result != 'OK':
                    logger.warning(f"Failed to fetch email ID {num.decode()}")
                    continue
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                email_list.append((num, msg))

            return mail, email_list

        except Exception as e:
            logger.error(f"Failed to fetch unseen emails: {e}")
            return None, []

    def forward_email(self, msg, smtp_config, forward_to):
        host = smtp_config['host']
        port = smtp_config['port']
        user = smtp_config['user']
        password = smtp_config['password']

        original_subject = self.sanitize_header(msg.get("Subject", "No Subject"))
        original_sender_name, original_sender_email = parseaddr(msg.get("From", ""))

        fwd = EmailMessage()
        fwd["From"] = formataddr((self.sanitize_header(original_sender_name), user))
        fwd["To"] = forward_to
        fwd["Subject"] = f"Fwd: {original_subject}"
        fwd["Reply-To"] = original_sender_email  # 保留原发件人作为回复地址

        footer = (
            "\n\n---------- Forwarded message ----------\n"
            f"From: {original_sender_name} {original_sender_email}\n"
            f"Subject: {original_subject}\n"
        )

        text_content = None
        html_content = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition") or "")

                # 忽略附件
                if "attachment" in content_disposition.lower():
                    continue

                payload = part.get_payload(decode=True)
                if not payload:
                    continue

                charset = part.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="ignore")

                if content_type == "text/plain" and text_content is None:
                    text_content = decoded
                elif content_type == "text/html" and html_content is None:
                    html_content = decoded
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                decoded = payload.decode(charset, errors="ignore")
                if msg.get_content_type() == "text/html":
                    html_content = decoded
                else:
                    text_content = decoded

        if text_content is None and html_content is None:
            text_content = "Empty content"

        text_body = (text_content or "") + footer
        fwd.set_content(text_body)

        if html_content:
            html_body = (html_content or "") + f"<br><br>{footer.replace(chr(10), '<br>')}"
            fwd.add_alternative(html_body, subtype='html')

        try:
            with smtplib.SMTP(host, port) as smtp:
                smtp.starttls()
                smtp.login(user, password)
                smtp.send_message(fwd)
                logger.success(
                    f"Successfully forwarded email to {forward_to}, sender_name: {original_sender_name}, sender_email: {original_sender_email}, subject: {original_subject}")
        except Exception as e:
            logger.error(f"Failed to forward email: {e}")

    @staticmethod
    def sanitize_header(value):
        return str(value).strip().replace("\n", "").replace("\r", "")

    def ack_email(self, mail, num, msg):
        """
        Mark the email as seen (acknowledged).
        """
        subject = self.sanitize_header(msg.get("Subject", "No Subject"))
        try:
            mail.store(num, '+FLAGS', '\\Seen')
            logger.info(f"Acknowledged email ID {num.decode()} (Subject: '{subject}')")
        except Exception as e:
            logger.error(f"Failed to acknowledge email ID {num.decode()} (Subject: '{subject}'): {e}")

    def start(self):
        """Starts the polling thread."""
        if self.running:
            logger.warning("Poller is already running.")
            return
        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """Stops the polling thread gracefully."""
        logger.info("Stopping email poller...")
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join()  # Wait for the thread to finish
        logger.info("Email poller stopped.")
