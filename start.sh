#!/usr/bin/env bash
set -e

# Ensure .streamlit directory exists
mkdir -p /app/.streamlit

# If all required auth env vars are present, write secrets.toml
if [[ -n "$STREAMLIT_AUTH_REDIRECT_URI" && \
      -n "$STREAMLIT_AUTH_COOKIE_SECRET" && \
      -n "$STREAMLIT_AUTH_MICROSOFT_CLIENT_ID" && \
      -n "$STREAMLIT_AUTH_MICROSOFT_CLIENT_SECRET" && \
      -n "$STREAMLIT_AUTH_MICROSOFT_SERVER_METADATA_URL" ]]; then
  cat > /app/.streamlit/secrets.toml <<EOF
[auth]
redirect_uri = "$STREAMLIT_AUTH_REDIRECT_URI"
cookie_secret = "$STREAMLIT_AUTH_COOKIE_SECRET"

[auth.microsoft]
client_id = "$STREAMLIT_AUTH_MICROSOFT_CLIENT_ID"
client_secret = "$STREAMLIT_AUTH_MICROSOFT_CLIENT_SECRET"
server_metadata_url = "$STREAMLIT_AUTH_MICROSOFT_SERVER_METADATA_URL"
EOF
  echo "Generated /app/.streamlit/secrets.toml from environment variables."
else
  echo "Warning: Missing one or more STREAMLIT_AUTH_* environment variables."
  echo "If secrets.toml exists in the image or mounted volume, it will be used."
fi

# Start Streamlit
exec streamlit run src/contract_analyzer_app.py --server.port=8501 --server.address=0.0.0.0
