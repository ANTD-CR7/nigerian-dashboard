"""
Pytest configuration: sets dummy Supabase credentials before `main.py` is
imported anywhere in the test suite.

main.py now requires SUPABASE_URL/SUPABASE_KEY to be set (no hardcoded
fallback -- see audit finding #1/#107: that fallback was the live anon key,
hardcoded, with RLS disabled on the tables it could write to). Tests never
touch a real database (network calls are monkeypatched out in test_main.py),
so these are dummy values, not real credentials.

SUPABASE_KEY must be JWT-shaped (three dot-separated base64url segments),
not just any string: a freshly-resolved `gotrue` (supabase's auth
sub-dependency) validates the key's format at create_client() time and
raises "Invalid API key" otherwise. An older gotrue resolution was more
lenient -- this only surfaced when testing a from-scratch dependency
install (see the fastapi/starlette/python-multipart CVE-fix upgrade), not
something the upgrade itself broke. The payload below decodes to
{"role": "anon"} and nothing else; it is not signed with a real secret and
cannot authenticate against any real Supabase project.
"""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.dGVzdC1zaWduYXR1cmUtbm90LXJlYWw",
)
