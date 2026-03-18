#!/usr/bin/env python3
"""
Setup script for encrypting the WeatherAPI key and creating .env file.
Run this after cloning the repo to securely configure the API key.
"""

import base64
import secrets
from cryptography.fernet import Fernet

def main():
    print("Weather Alert System - Environment Setup")
    print("=========================================")
    
    # Get API key from user
    api_key = input("Enter your WeatherAPI key: ").strip()
    if not api_key:
        print("Error: API key cannot be empty.")
        return
    
    # Generate encryption key
    encryption_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    
    # Encrypt the API key
    f = Fernet(encryption_key.encode())
    encrypted_api_key = f.encrypt(api_key.encode()).decode()
    
    # Write to .env
    with open('.env', 'w') as env_file:
        env_file.write(f'ENCRYPTION_KEY={encryption_key}\n')
        env_file.write(f'ENCRYPTED_API_KEY={encrypted_api_key}\n')
    
    print("\n✅ Setup complete!")
    print("Your API key has been encrypted and saved to .env")
    print("You can now run the application with: python main.py")
    print("\n⚠️  Important: Keep .env secure and never commit it to version control.")

if __name__ == "__main__":
    main()