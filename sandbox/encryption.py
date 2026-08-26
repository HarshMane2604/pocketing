import os
import sys

# The key used for XOR encryption/decryption
KEY = b"t8yA7xR9uW3mP5qK2vB4nS6zD8jF0hG1"

def xor_crypt_data(data: bytes, key: bytes) -> bytes:
    """Encrypts or decrypts data using a basic XOR cipher with a repeating key."""
    key_len = len(key)
    return bytes(data[i] ^ key[i % key_len] for i in range(len(data)))

def process_file(file_path: str, key: bytes):
    """Reads a file, applies XOR cipher in-place."""
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        
        crypted_data = xor_crypt_data(data, key)
        
        with open(file_path, 'wb') as f:
            f.write(crypted_data)
            
        print(f"Successfully processed: {file_path}")
    except Exception as e:
        print(f"Failed to process {file_path}: {e}")

def process_directory(directory: str, key: bytes, exclude_script: str = None):
    """Recursively crawls the directory and processes all files."""
    for root, _, files in os.walk(directory):
        for file in files:
            file_path = os.path.join(root, file)
            # Skip the script itself if it's placed inside the directory
            if exclude_script and os.path.abspath(file_path) == os.path.abspath(exclude_script):
                continue
            process_file(file_path, key)

if __name__ == "__main__":
    # Path to your sandbox directory
    # SANDBOX_DIR = "/home/harsh/pocketing/pocketing/sandbox/pocketing_sandbox"
    SANDBOX_DIR = "/home/harsh/pocketing/pocketing/sandbox"

    print(f"Key loaded: {KEY.decode('utf-8')}")
    print(f"Target Sandbox: {SANDBOX_DIR}")
    print("-" * 50)
    print("WARNING: Running this script will encrypt/decrypt files in-place.")
    print("Running it once encrypts; running it again on the encrypted files decrypts them.")
    print("-" * 50)
    
    # Automatically accept for demonstration
    proceed = True
    
    if proceed:
        script_path = sys.argv[0]
        process_directory(SANDBOX_DIR, KEY, exclude_script=script_path)
        print("Processing complete!")
    else:
        print("Operation cancelled.")
