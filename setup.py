#!/usr/bin/env python3
"""
Initial setup script for LeadGen System
Helps configure all required credentials and creates necessary directories
"""

import os
import json
import sys
import shutil
from pathlib import Path

def create_directory_structure():
    """Create necessary directories"""
    directories = [
        'data',
        'credentials',
        'logs',
        'data/leads',
        'data/demos',
        'data/cache',
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ Created directory: {directory}")

def create_env_file():
    """Create .env file template"""
    env_content = """# LeadGen System Environment Configuration

# === Google Sheets Configuration ===
GOOGLE_SHEETS_CREDENTIALS_PATH=credentials/google-service-account.json
GOOGLE_SHEETS_ID=  # Your Google Sheets ID here

# === Email Configuration (SMTP) ===
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=  # Your sending email address
SMTP_PASSWORD=  # Your app password (NOT your regular password)
SMTP_USE_TLS=true

# === Instagram Configuration ===
INSTA_USERNAME=  # Dedicated Instagram account for outreach
INSTA_PASSWORD=  # Instagram account password

# === Apify Configuration (Optional) ===
# Get your key from: https://console.apify.com/
APIFY_API_KEY=  # Leave blank if not using Apify

# === System Settings ===
DEBUG=true
LOG_LEVEL=INFO
"""

    with open('.env', 'w') as f:
        f.write(env_content)
    print("✓ Created .env file template")
    print("  → Please edit this file with your credentials")

def create_requirements_file():
    """Create requirements.txt"""
    packages = [
        "requests>=2.31.0",
        "beautifulsoup4>=4.12.3",
        "selenium>=4.17.2",
        "lxml>=5.1.0",
        "pandas>=2.2.0",
        "python-dateutil>=2.9.0",
        "google-auth>=2.27.0",
        "google-auth-oauthlib>=1.2.0",
        "google-api-python-client>=2.116.0",
        "jinja2>=3.1.3",
        "python-dotenv>=1.0.0",
        "webdriver-manager>=4.1.4",
        "tqdm>=4.66.2",
    ]

    with open('requirements.txt', 'w') as f:
        f.write('\n'.join(packages))
    print("✓ Created requirements.txt")

def print_gcloud_instructions():
    """Print Google Cloud setup instructions"""
    print("\n" + "="*60)
    print(" GOOGLE CLOUD SETUP INSTRUCTIONS")
    print("="*60)
    print("""
1. Go to: https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable APIs:
   - Google Sheets API
   - Google Drive API
4. Go to: IAM & Admin > Service Accounts
5. Create Service Account:
   - Name: leadgen-system
   - Role: Project > Editor
6. Create Key:
   - Type: JSON
   - Download and save as: credentials/google-service-account.json
7. Create a Google Sheet and share it with:
   - The service account email (from JSON file)
   - Make sure it has "Editor" permissions
8. Copy the Sheet ID from the URL into your .env file:
   https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID_HERE/edit
""")

def print_gmail_instructions():
    """Print Gmail setup instructions"""
    print("\n" + "="*60)
    print(" GMAIL SMTP SETUP INSTRUCTIONS")
    print("="*60)
    print("""
If using Gmail for email outreach:

1. Enable 2-Factor Authentication on your Gmail account
2. Go to: https://myaccount.google.com/apppasswords
3. Generate an "App Password"
4. Use the app password as SMTP_PASSWORD in your .env file
5. Recommended: Create a separate Gmail account for this system

Note: Free Gmail accounts have a 500 emails/day limit
For higher volume, consider Google Workspace or a dedicated email service.
""")

def print_instagram_instructions():
    """Print Instagram setup instructions"""
    print("\n" + "="*60)
    print(" INSTAGRAM SETUP INSTRUCTIONS")
    print("="*60)
    print("""
For Instagram DM automation:

1. Create a NEW Instagram account dedicated to outreach
2. DO NOT use your main personal account
3. Add a profile picture and bio (appears more legitimate)
4. Add username/password to your .env file
5. Chrome/Chromedriver will be needed (auto-installed by webdriver-manager)

Warning: Instagram may temporarily block accounts using automation.
Use cautiously on non-personal accounts.
""")

def print_apify_instructions():
    """Print Apify setup instructions"""
    print("\n" + "="*60)
    print(" APIFY SETUP (Optional)")
    print("="*60)
    print("""
For Zillow/Realtor.com scraping:

1. Go to: https://apify.com/
2. Sign up for a free account (includes 10 free credits/month)
3. Go to: https://console.apify.com/integrations
4. Copy your API Key
5. Paste it into your .env file as APIFY_API_KEY

Alternative: Direct scraping is available without Apify (slower, may hit rate limits)
""")

def main():
    """Run setup"""
    print("LeadGen System Setup")
    print("="*60)

    # Create directories
    create_directory_structure()

    # Create config files
    create_env_file()
    create_requirements_file()

    # Print setup instructions
    print_gcloud_instructions()
    print_gmail_instructions()
    print_instagram_instructions()
    print_apify_instructions()

    # Create sample config file
    sample_config = {
        "version": "0.1.0",
        "setup_completed": False,
        "setup_steps": [
            "Create .env file with credentials",
            "Set up Google Cloud project",
            "Configure Gmail SMTP credentials",
            "Create Instagram account for outreach",
            "Optionally configure Apify API key",
            "Install requirements: pip install -r requirements.txt",
            "Run system: python -m leadgen.main"
        ]
    }

    with open('config/setup_status.json', 'w') as f:
        json.dump(sample_config, f, indent=2)

    print("\n✅ Setup complete!")
    print("\nNext steps:")
    print("  1. Edit .env file with your credentials")
    print("  2. Install dependencies: pip install -r requirements.txt")
    print("  3. Run the system: python -m leadgen.main")
    print("\nSee README.md for full documentation.")

if __name__ == '__main__':
    main()