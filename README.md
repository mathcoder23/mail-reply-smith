# mail-reply-smith

A Python-based mail relay and filter supporting IMAP/SMTP with easy Docker deployment. This tool periodically checks an IMAP inbox, processes emails based on custom rules, and can send replies or forward emails via an SMTP server.

## Features

- **IMAP Integration**: Fetches unread emails from a specified IMAP server.
- **SMTP Relay**: Sends emails (replies, forwards) through a configured SMTP server.
- **Customizable Filtering**: Process incoming emails based on user-defined rules.
- **Dockerized**: Comes with a `Dockerfile` and `docker-compose.yml` for quick and isolated deployment.
- **Extensible**: Built with Python, making it easy to extend and customize the filtering and action logic.

## How It Works

The application operates in a continuous loop:

1.  **Connect & Fetch**: It connects to the configured IMAP server and fetches unread emails from the INBOX.
2.  **Filter & Process**: Each new email is passed through a series of user-defined filters. These filters can check for sender, subject, body content, etc.
3.  **Take Action**: If an email matches a filter's criteria, a corresponding action is triggered. This could be sending an automated reply, forwarding the email, or simply marking it as read.
4.  **Send Mail**: Actions that require sending an email use the configured SMTP server.
5.  **Wait**: After a cycle, the application waits for a configurable interval before checking for new emails again.

## Prerequisites

- Docker
- Docker Compose
- An email account with IMAP and SMTP access.

## Getting Started

Follow these steps to get your `mail-reply-smith` instance up and running.

### 1. Clone the Repository

If you haven't already, clone the project repository:

```bash
git clone https://github.com/mathcoder23/mail-reply-smith
cd mail-reply-smith
```

### 2. Configure the Application

The application's behavior is controlled by the `src/config/config.yaml` file. You'll need to edit this file to set up your email accounts and define filtering rules.

Open `src/config/config.yaml` and update the following sections:

#### Transport Configuration

This section is for your IMAP (incoming) and SMTP (outgoing) server details.

```yaml
transport_config:
  imap:
    host: "imap.yourprovider.com"
    port: 993
    user: "your_email@example.com"
    password: "your_imap_password"
    is_fix_163provider_issue: true # Set to true if you use a 163.com provider
  smtp:
    host: "smtp.yourprovider.com"
    port: 587 # Or 465, 25 depending on your provider
    user: "your_email@example.com"
    password: "your_smtp_password"
```

#### Application Behavior and Rules

Configure how the application fetches emails and define your filtering rules in the `filters` section.

```yaml
pull_email:
  fetch_interval_seconds: 60 # Check for new mail every 60 seconds
  transport: imap # Should be 'imap'
  select_folder: INBOX # The IMAP folder to watch
  keep_unseen_count: 50 # Number of recent unseen emails to keep track of

filters:
  # Forward emails from specific senders
  - sender_email_contains: ["@work-domain.com", "important-sender@email.com"]
    action: "forward"
    forward_to: "your_other_email@example.com"
```

### 3. Run with Docker

Once configured, you can start the service using Docker Compose:

```bash
./start-docker-compose.sh
```

alternative: `./start-docker.sh` or `./start-local.sh`

The service will now be running in the background. You can check its logs with:

```bash
docker-compose logs -f
```

To stop the service:

```bash
docker-compose down
```

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## License

[MIT License](https://github.com/mathcoder23/mail-reply-smith/blob/main/LICENSE)
