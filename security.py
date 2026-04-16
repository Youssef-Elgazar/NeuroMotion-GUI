import os
from cryptography.fernet import Fernet

KEY_FILE = "Master_Encryption_Key.key"

class SecureSessionVault:
    def __init__(self, output_dir="Secure_Session_Logs"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)
        
    def _load_or_create_key(self):
        # We store the encryption key near the executing path; the user should keep it safe.
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(KEY_FILE, "wb") as f:
                f.write(key)
            return key
            
    def encrypt_data(self, json_string):
        """Encrypt JSON string to bytes."""
        return self.cipher.encrypt(json_string.encode('utf-8'))
        
    def decrypt_data(self, encrypted_bytes):
        """Decrypt bytes back to string."""
        return self.cipher.decrypt(encrypted_bytes).decode('utf-8')
