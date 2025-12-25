from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import serialization
import os


class CryptKeeper:
    def __init__(self, private_key=None):
        # Generate a new private key if one is not provided
        self.private_key = private_key or ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()

    def get_serialized_public_key(self):
        # Returns public key in PEM format for sharing
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def load_peer_public_key(self, peer_public_bytes):
        # Load peer's public key from PEM
        return serialization.load_pem_public_key(peer_public_bytes)

    def derive_shared_key(self, peer_public_key):
        # Use ECDH to derive a shared secret, then use HKDF to get an AES key
        shared_secret = self.private_key.exchange(ec.ECDH(), peer_public_key)
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,  # 256 bits AES key
            salt=None,
            info=b'handshake data'
        ).derive(shared_secret)
        return derived_key

    def encrypt(self, plaintext: bytes, peer_public_key) -> (bytes, bytes):
        # Encrypt using a key derived from peer's public key
        key = self.derive_shared_key(peer_public_key)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)  # AESGCM standard nonce size
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce, ciphertext

    def decrypt(self, nonce: bytes, ciphertext: bytes, peer_public_key) -> bytes:
        # Decrypt using a key derived from peer's public key
        key = self.derive_shared_key(peer_public_key)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext, None)

    def export_private_key(self, password=None):
        # Export private key in PEM format (optionally encrypted with password)
        encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=encryption
        )

    @staticmethod
    def load_private_key(pem_bytes, password=None):
        # Load a private key from PEM
        private_key = serialization.load_pem_private_key(pem_bytes, password=password)
        return CryptKeeper(private_key=private_key)


def main():
    # Alice and Bob generate their own key pairs
    alice = CryptKeeper()
    bob = CryptKeeper()
    # Exchange public keys
    bob_pub = bob.get_serialized_public_key()
    alice_pub = alice.get_serialized_public_key()
    # Alice loads Bob's public key
    bob_pubkey_obj = alice.load_peer_public_key(bob_pub)
    # Bob loads Alice's public key
    alice_pubkey_obj = bob.load_peer_public_key(alice_pub)
    # Alice encrypts a message to Bob
    nonce, ciphertext = alice.encrypt(b"Secret message!", bob_pubkey_obj)
    # Bob decrypts the message from Alice
    plaintext = bob.decrypt(nonce, ciphertext, alice_pubkey_obj)
    print("Decrypted:", plaintext.decode())


# Example usage:
if __name__ == "__main__":
    main()
