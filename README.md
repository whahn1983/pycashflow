![logo](./app/static/apple-touch-icon.png)

# PyCashFlow

[![Build Status](https://scrutinizer-ci.com/g/whahn1983/pycashflow/badges/build.png?b=master)](https://scrutinizer-ci.com/g/whahn1983/pycashflow/build-status/master)
![Docker Pulls](https://img.shields.io/docker/pulls/whahn1983/pycashflow)
![GitHub License](https://img.shields.io/github/license/whahn1983/pycashflow)

**A comprehensive Python Flask application for cash flow forecasting, transaction management, and financial planning.**

PyCashFlow is a powerful, multi-user web application designed to help individuals and families manage their finances through intelligent cash flow forecasting, recurring transaction scheduling, and automated balance tracking. With support for up to one year of cash flow projections, interactive visualizations, and automatic email-based balance updates, PyCashFlow provides a complete solution for financial planning and management.

<img width="912" height="880" alt="PyCashFlow Dashboard" src="https://github.com/user-attachments/assets/72acb38c-1e60-474e-8d86-b25854d83e59" />

---

## Table of Contents

- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [Installation](#installation)
  - [Docker Installation (Recommended)](#docker-installation-recommended)
  - [Manual Installation](#manual-installation)
- [Configuration](#configuration)
- [User Roles & Access Control](#user-roles--access-control)
- [Core Capabilities](#core-capabilities)
- [Email Integration](#email-integration)
- [Data Management](#data-management)
- [Updates & Maintenance](#updates--maintenance)
- [Professional Support](#professional-support)
- [Built With](#built-with)
- [License](#license)

---

## Key Features

### Cash Flow Forecasting & Visualization
- **12-Month Projections**: Visualize your future cash flow up to one year in advance
- **Interactive Charts**: Plotly-powered interactive visualizations with zoom, pan, and hover details
- **Minimum Balance Warnings**: Automatically identifies potential low balance periods
- **60-Day Transaction Preview**: Detailed view of upcoming transactions with running balance calculations

### Transaction Management
- **Recurring Schedules**: Support for multiple frequencies:
  - Monthly, Weekly, BiWeekly, Quarterly, Yearly, and One-Time transactions
- **Smart Date Handling**: Automatic business day adjustments for weekends
- **Transaction Holds**: Temporarily pause scheduled transactions without deletion
- **Skip Functionality**: Skip individual future transaction instances
- **Manual Balance Updates**: Set account balance for any specific date
- **Auto-Cleanup**: One-time transactions automatically removed after their date passes

### Multi-User Support
- **Three-Tier Access Control**:
  - **Global Administrator**: System-wide management and user approval
  - **Account Owner**: Full cash flow management plus guest user administration
  - **Guest User**: View-only dashboard access for family members or advisors
- **User Activation Workflow**: Global admin approval required for new registrations
- **Multi-Account Isolation**: Complete data separation between account owners

### Automated Balance Updates
- **IMAP Email Integration**: Automatically extract balance information from bank emails
- **Configurable Search**: Customizable subject lines and balance delimiter patterns
- **Scheduled Processing**: Automated cron job checks emails every minute
- **Multi-User Support**: Per-user email configurations and processing

### Modern Authentication
- **Traditional Login**: Email/password authentication with Scrypt password hashing
- **Passkey Support**: Modern passwordless authentication via Corbado integration
- **Session Management**: Secure session handling with "remember me" functionality

### Progressive Web App (PWA)
- **Installable**: Add to home screen on mobile and desktop devices
- **Service Worker**: Enhanced performance and offline capabilities
- **Mobile Optimized**: Responsive design for all screen sizes

---

## Technology Stack

### Backend
- **Flask**: Lightweight Python web framework
- **SQLAlchemy**: SQL toolkit and ORM for database management
- **Flask-Migrate**: Database migration management
- **Waitress**: Production-ready WSGI server
- **Flask-Login**: User session management

### Data Processing
- **Pandas**: Data manipulation and transaction calculations
- **NumPy**: Numerical operations and array processing
- **Python-dateutil**: Advanced date arithmetic and business day logic

### Frontend & Visualization
- **Plotly**: Interactive, responsive charting library
- **Bootstrap**: Responsive UI framework
- **HTML/CSS/JavaScript**: Modern web standards

### Security
- **Werkzeug**: Scrypt password hashing
- **Corbado SDK**: Passkey authentication (optional)
- **python-dotenv**: Secure environment variable management

### Email & Notifications
- **IMAPLIB**: Email retrieval from mail servers
- **SMTPLIB**: Email sending for notifications
- **Python email library**: MIME message parsing and creation

### Infrastructure
- **Docker**: Containerization for easy deployment
- **Alpine Linux**: Lightweight container base image
- **Cron**: Scheduled task execution
- **SQLite/PostgreSQL**: Flexible database options

---

## Installation

### Docker Installation (Recommended)

Docker provides the simplest and most reliable deployment method for PyCashFlow.

#### Pull the Latest Image

```bash
docker pull whahn1983/pycashflow:latest
```

#### Run the Container

```bash
docker run -d \
  -p 127.0.0.1:5000:5000 \
  -v /mnt/data:/app/app/data \
  -v /mnt/migrations:/app/migrations \
  -v /etc/localtime:/etc/localtime:ro \
  -v /mnt/.env:/app/app/.env \
  --restart always \
  --pull always \
  --name pycashflow \
  whahn1983/pycashflow:latest
```

#### Volume Explanations

| Volume Mount | Purpose | Required |
|--------------|---------|----------|
| `/mnt/data:/app/app/data` | Persistent database storage | **Yes** |
| `/mnt/migrations:/app/migrations` | Database migration files | Recommended |
| `/etc/localtime:/etc/localtime:ro` | Correct timezone for calculations | Recommended |
| `/mnt/.env:/app/app/.env` | Environment variables (Corbado, etc.) | Optional |

#### Access the Application

Once running, access PyCashFlow at `http://localhost:5000`

---

### Manual Installation

For advanced users or custom deployments, PyCashFlow can be installed directly on a server.

#### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)
- Git
- WSGI server (Waitress, Gunicorn, or uWSGI)
- (Optional) Reverse proxy (Nginx or Apache)

#### Installation Steps

1. **Clone the Repository**
   ```bash
   git clone https://github.com/whahn1983/pycashflow.git
   cd pycashflow
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize Database**
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

4. **Configure Environment Variables**

   Create a `.env` file in `/app/app/.env`:
   ```bash
   # Optional: For Passkey Authentication
   PROJECT_ID=your_corbado_project_id
   API_SECRET=your_corbado_api_secret
   FRONTEND_URI=https://your-domain.com

   # Optional: Database URL (defaults to SQLite)
   DATABASE_URL=sqlite:///data/db.sqlite
   ```

5. **Run the Application**

   Using Waitress (included):
   ```bash
   python app.py
   ```

   Or with Gunicorn:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
   ```

6. **Configure Email Processing (Optional)**

   Set up a cron job to run email balance imports:
   ```bash
   crontab -e
   ```

   Add the following line:
   ```
   * * * * * cd /path/to/pycashflow && python3 app/getemail.py
   ```

7. **Set Up Reverse Proxy (Recommended)**

   For production deployments, configure Nginx or Apache to proxy requests to the WSGI server on port 5000.

---

## Configuration

### First-Time Setup

1. **Access the Application**: Navigate to `http://your-server:5000`
2. **Create First User**: Sign up with email and password
3. **Activate Global Admin**: The first user is automatically approved and designated as Global Administrator
4. **Configure Email Settings** (Optional):
   - Navigate to Settings → Email Configuration
   - Enter IMAP server details for automatic balance updates
   - Configure search parameters (subject line, balance delimiters)

### User Management

#### As Global Administrator
- Approve or deny new user registrations
- Activate/deactivate user accounts
- Configure system-wide email settings for notifications
- Enable/disable new user signups

#### As Account Owner
- Manage guest users for your account
- Add guest users with view-only dashboard access
- Remove guest users when access is no longer needed

---

## User Roles & Access Control

PyCashFlow implements a three-tier access control system:

### Global Administrator
- **Full System Access**: Manage all users and system settings
- **User Approval**: Activate or deactivate user accounts
- **Email Configuration**: Set up system notification emails
- **Cannot Be Deactivated**: Ensures system always has an administrator

### Account Owner
- **Full Cash Flow Management**: Create, edit, and delete schedules
- **Balance Management**: Manual and automated balance updates
- **Guest User Management**: Create and manage view-only users
- **Data Management**: Import/export transaction schedules

### Guest User
- **Dashboard Access Only**: View cash flow chart and current balance
- **No Editing Permissions**: Cannot modify schedules or settings
- **Requires Activation**: Must be activated by account owner before access

---

## Core Capabilities

### Cash Flow Calculation Engine

PyCashFlow's sophisticated calculation engine (`/app/cashflow.py`) provides:

- **Multi-Frequency Support**: Handles Monthly, Weekly, BiWeekly, Quarterly, Yearly, and One-Time transactions
- **Business Day Logic**: Automatically adjusts transaction dates for weekends
  - Income transactions: Rolled back to last business day
  - Expense transactions: Advanced to next business day
- **Hold Management**: Temporarily pause scheduled transactions
- **Skip Functionality**: Skip individual future instances without affecting the entire schedule
- **Running Balance Projections**: Calculate balance for every day up to 12 months ahead
- **Automatic Cleanup**: Remove past one-time transactions

### Transaction Scheduling

Create and manage recurring financial events:

- **Flexible Frequencies**: Choose from multiple recurrence patterns
- **Custom Amounts**: Set precise transaction amounts
- **Income vs Expense**: Categorize transactions for accurate projections
- **Hold Until Date**: Temporarily suspend transactions
- **Skip Future Instances**: One-time skips without schedule deletion

### Balance Tracking

Multiple methods for keeping your balance current:

- **Manual Entry**: Set balance for any specific date
- **Email Import**: Automatic extraction from bank notification emails
- **Historical Tracking**: View balance history over time

---

## Email Integration

### Automated Balance Updates

PyCashFlow can automatically update your account balance by reading bank notification emails.

#### Configuration Steps

1. Navigate to **Settings → Email Configuration**
2. Enter your email credentials:
   - IMAP server address
   - Email address
   - Password (stored securely)
3. Configure search parameters:
   - Email subject to search for (e.g., "Balance Alert")
   - Balance start delimiter (text before balance)
   - Balance end delimiter (text after balance)
4. Save configuration

#### How It Works

- Cron job runs every minute (Docker) or as configured (manual installation)
- Searches for emails from the past 24 hours matching your subject
- Extracts balance using your configured delimiters
- Updates your account balance automatically
- Processes all users independently (one failure doesn't affect others)

### System Notifications

PyCashFlow sends email notifications for:

- **New User Registrations**: Alerts global admin when someone signs up
- **Account Activation**: Notifies user when their account is approved

---

## Data Management

### Export Schedules

Export your transaction schedules to CSV format:

1. Navigate to **Schedule → Export**
2. Download CSV file with all scheduled transactions
3. Use for backup, analysis, or migration

### Import Schedules

Import schedules from CSV files:

1. Prepare CSV file with columns: `name`, `amount`, `frequency`, `type`, `day`
2. Navigate to **Schedule → Import**
3. Select CSV file and upload
4. Existing schedules are preserved; new entries are added

### Data Portability

All data is stored in SQLite (default) or PostgreSQL database with full export capabilities.

---

## Updates & Maintenance

### Updating Docker Installation

```bash
docker pull whahn1983/pycashflow:latest
docker stop pycashflow
docker rm pycashflow
# Run the docker run command again with your volume mounts
```

### Updating Manual Installation

```bash
cd /path/to/pycashflow
git pull origin master
flask db migrate -m "Update migration"
flask db upgrade
# Restart your WSGI server
```

### Database Migrations

PyCashFlow uses Flask-Migrate for database schema management:

- Migrations are automatically generated when database models change
- Mount `/mnt/migrations` volume (Docker) to persist migration files
- Run `flask db upgrade` after pulling updates

---

## Professional Support

### H3 Consulting Partners LLC

For professional installation, configuration, ongoing support, and accelerated development of PyCashFlow, contact **H3 Consulting Partners LLC**.

**Services Offered:**
- Professional installation and deployment
- Custom configuration for your environment
- Integration with existing financial systems
- Feature development and customization
- Ongoing maintenance and support
- Training and documentation

**Contact Information:**
- **Email**: [bill@h3consultingpartners.com](mailto:bill@h3consultingpartners.com)
- **Website**: [https://h3consultingpartners.com](https://h3consultingpartners.com)

H3 Consulting Partners specializes in enterprise deployments, custom feature development, and ongoing support to ensure PyCashFlow meets your organization's specific needs.

---

## Built With

[<img src="https://resources.jetbrains.com/storage/products/company/brand/logos/PyCharm.png" alt="PyCharm logo." width="300">](https://jb.gg/OpenSourceSupport)

---

## License

This project is licensed under the terms specified in the [LICENSE](LICENSE) file.

---

## Repository

**GitHub**: [https://github.com/whahn1983/pycashflow](https://github.com/whahn1983/pycashflow)

**Docker Hub**: [https://hub.docker.com/r/whahn1983/pycashflow](https://hub.docker.com/r/whahn1983/pycashflow)

---

## Version

**Current Version**: 3.2.3

---

*PyCashFlow - Professional cash flow management and forecasting for individuals and families.*
