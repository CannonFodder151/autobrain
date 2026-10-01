#!/usr/bin/env python3
"""AUT-2241: seed-secrets.sh must not silently overwrite existing secrets."""
import os
import subprocess
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed-secrets.sh")
ENV_DUMP = "POSTGRES_PASSWORD=from-env-dump\nREDIS_PASSWORD=also-from-dump\nUNMAPPED_KEY=x\n"


def run(secrets_dir, env_file, **extra):
    e = dict(os.environ)
    e.pop("SEED_ALLOW_OVERWRITE", None)
    e.update(extra)
    return subprocess.run(
        ["sh", SCRIPT, env_file, secrets_dir],
        capture_output=True, text=True, env=e, check=True,
    ).stdout


def main():
    with tempfile.TemporaryDirectory() as d:
        env_file = os.path.join(d, "stack-env.txt")
        with open(env_file, "w") as f:
            f.write(ENV_DUMP)

        # First run seeds.
        out = run(d, env_file)
        pw = os.path.join(d, "postgres_password")
        assert open(pw).read() == "from-env-dump", out
        assert "seeded" in out and pw in out, out

        # Second run with a different dump must NOT change the file (AUT-2241).
        with open(env_file, "w") as f:
            f.write("POSTGRES_PASSWORD=rotated-in-portainer\nREDIS_PASSWORD=rotated-too\n")
        out = run(d, env_file)
        assert open(pw).read() == "from-env-dump", "secret was overwritten: " + out
        assert "KEEP" in out and pw in out, out

        # Opt-in overwrite still works for a deliberate rotation.
        out = run(d, env_file, SEED_ALLOW_OVERWRITE="1")
        assert open(pw).read() == "rotated-in-portainer", out
        assert "seeded" in out, out

    print("ok - seed-secrets.sh preserves existing secrets unless forced")


if __name__ == "__main__":
    main()