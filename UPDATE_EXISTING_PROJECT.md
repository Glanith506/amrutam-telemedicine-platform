# Update your existing project and keep your data

Use your ORIGINAL folder:
C:\Users\Acer\Downloads\Amrutam_Backend_Assignment\amrutam-backend

1. Extract this ZIP into a temporary folder.
2. In your original project terminal, run `docker compose down` WITHOUT -v.
3. Copy frontend/ and backend/ from this ZIP into that original project folder.
4. Also copy compose.yaml and .dockerignore, REPLACING the old versions.
   You can also merge/replace scripts/, infra/, docs/ and .github/ as needed.
5. Keep your ORIGINAL .env unchanged. Do not regenerate its encryption key.
6. Run `docker compose up --build -d` from that ORIGINAL project folder.
7. Open http://localhost:8000/.

Your old top-level app/ folder and root Dockerfile are no longer used. You can leave
them until you verify the update: the new Dockerfile copies only backend/app.
Do not place frontend/ or backend/ inside the old app/ folder.

Keeping the original folder/project name preserves your current Compose pgdata volume.
Do not run Compose from the temporary extracted folder if you want existing records.
Never run docker compose down -v unless intentionally deleting your database.
