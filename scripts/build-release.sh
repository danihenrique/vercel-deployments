#!/bin/bash
# Build script for vercel-deployments .deb package

set -e

echo "Building vercel-deployments .deb package..."

# Clean previous builds
rm -f ../vercel-deployments_*.deb ../vercel-deployments_*.buildinfo ../vercel-deployments_*.changes

# Build the .deb package
dpkg-buildpackage -us -uc -b

# Find the generated .deb file
DEB_FILE=$(ls ../vercel-deployments_*.deb | head -1)

if [ -f "$DEB_FILE" ]; then
    echo "✅ Package built successfully: $DEB_FILE"
    echo "📦 File size: $(du -h "$DEB_FILE" | cut -f1)"
    echo ""
    echo "To install:"
    echo "  sudo dpkg -i $DEB_FILE"
    echo ""
    echo "For GitHub release, upload:"
    echo "  $DEB_FILE"
else
    echo "❌ No .deb file found!"
    exit 1
fi
