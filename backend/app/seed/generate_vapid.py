"""Generate VAPID keys for Web Push. Paste the output into backend/.env.

Run: python -m app.seed.generate_vapid
"""

from app.services.push import generate_vapid_keys

if __name__ == "__main__":
    public, private = generate_vapid_keys()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    print("VAPID_SUBJECT=mailto:you@your-organisation.org")
