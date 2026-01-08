#!/usr/bin/env bash
set -e

echo "=== Contract Analyzer Startup ==="
echo "Working directory: $(pwd)"
echo "Creating .streamlit directory..."

# Ensure .streamlit directory exists
mkdir -p /app/.streamlit

# Debug: Print all STREAMLIT_* variables (without secrets)
echo "Checking environment variables..."
echo "STREAMLIT_AUTH_REDIRECT_URI: ${STREAMLIT_AUTH_REDIRECT_URI:-(not set)}"
echo "STREAMLIT_AUTH_COOKIE_SECRET: ${STREAMLIT_AUTH_COOKIE_SECRET:+(set)}"
echo "STREAMLIT_AUTH_MICROSOFT_CLIENT_ID: ${STREAMLIT_AUTH_MICROSOFT_CLIENT_ID:-(not set)}"
echo "STREAMLIT_AUTH_MICROSOFT_CLIENT_SECRET: ${STREAMLIT_AUTH_MICROSOFT_CLIENT_SECRET:+(set)}"
echo "STREAMLIT_AUTH_MICROSOFT_SERVER_METADATA_URL: ${STREAMLIT_AUTH_MICROSOFT_SERVER_METADATA_URL:-(not set)}"
echo "AUTH_DISABLED: ${AUTH_DISABLED:-(not set)}"

# If all required auth env vars are present, write secrets.toml
if [[ -n "$STREAMLIT_AUTH_REDIRECT_URI" && \
      -n "$STREAMLIT_AUTH_COOKIE_SECRET" && \
      -n "$STREAMLIT_AUTH_MICROSOFT_CLIENT_ID" && \
      -n "$STREAMLIT_AUTH_MICROSOFT_CLIENT_SECRET" && \
      -n "$STREAMLIT_AUTH_MICROSOFT_SERVER_METADATA_URL" ]]; then
  
  echo "Generating /app/.streamlit/secrets.toml from environment variables..."
  
  cat > /app/.streamlit/secrets.toml <<EOF
[auth]
redirect_uri = "$STREAMLIT_AUTH_REDIRECT_URI"
cookie_secret = "$STREAMLIT_AUTH_COOKIE_SECRET"

[auth.microsoft]
client_id = "$STREAMLIT_AUTH_MICROSOFT_CLIENT_ID"
client_secret = "$STREAMLIT_AUTH_MICROSOFT_CLIENT_SECRET"
server_metadata_url = "$STREAMLIT_AUTH_MICROSOFT_SERVER_METADATA_URL"
EOF
  
  # Ensure correct permissions
  chmod 600 /app/.streamlit/secrets.toml
  
  echo "✓ /app/.streamlit/secrets.toml created successfully"
  echo "Verifying secrets.toml content..."
  if grep -q "client_id" /app/.streamlit/secrets.toml; then
    echo "✓ secrets.toml is valid"
  else
    echo "✗ Error: secrets.toml does not contain expected content"
    exit 1
  fi
else
  echo "⚠ Warning: Missing one or more STREAMLIT_AUTH_* environment variables"
  
  # Check if secrets.toml already exists (from volume mount or image build)
  if [[ -f "/app/.streamlit/secrets.toml" ]]; then
    echo "✓ Found existing /app/.streamlit/secrets.toml from volume/image"
  else
    echo "✗ No secrets.toml found and required env vars not set"
    echo "  To fix: Set all STREAMLIT_AUTH_* environment variables in Container App"
    echo "  Or: Mount a .streamlit/secrets.toml volume"
    exit 1
  fi
fi

echo ""
echo "Starting Streamlit application..."
echo "Port: 8501, Address: 0.0.0.0"
echo "===================================="
echo ""

# Start Streamlit
exec streamlit run src/contract_analyzer_app.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  --logger.level=debug

