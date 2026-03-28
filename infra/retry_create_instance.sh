#!/bin/bash
# Retries creating the ARM instance until capacity is available.
# Run this in Oracle Cloud Shell.

AD="uMxE:AF-JOHANNESBURG-1-AD-1"
COMPARTMENT_ID="ocid1.tenancy.oc1..aaaaaaaap2lw6ehhztvxwgcecglcpaw7wxiluorq7j2xs3uupe6ywbvdfw2a"
SUBNET_ID="ocid1.subnet.oc1.af-johannesburg-1.aaaaaaaal6dm4pcgey3hobknyebsi4y2ylqfjcs5hqv36ghmvbzwz5bx34qa"
IMAGE_ID="ocid1.image.oc1.af-johannesburg-1.aaaaaaaahqmbhyldeypb367h46pbtsbyfk3mnbovrjr5q2eiq2bvtchnhxfq"

SSH_KEYS="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGxeOhB7gP5biZ7xXPSQGrVdCAeZNQjRTHoClbQgjPAB donfolayan@gmail.com
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFnjhpRwSA4Xr/JjPzspohjVFK5llfg32/4oiYy2J3tk oracle-waha"

echo "Starting retry loop for VM.Standard.A1.Flex in $AD"
echo "Press Ctrl+C to stop."

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Attempting to create instance..."

    oci compute instance launch \
        --availability-domain "$AD" \
        --compartment-id "$COMPARTMENT_ID" \
        --shape "VM.Standard.A1.Flex" \
        --shape-config '{"memoryInGBs": 6, "ocpus": 1}' \
        --subnet-id "$SUBNET_ID" \
        --image-id "$IMAGE_ID" \
        --display-name "Waha" \
        --assign-public-ip true \
        --metadata "{\"ssh_authorized_keys\": \"$SSH_KEYS\"}" \
        --availability-config '{"recoveryAction": "RESTORE_INSTANCE"}' \
        --instance-options '{"areLegacyImdsEndpointsDisabled": false}' \
        --wait-for-state RUNNING

    if [ $? -eq 0 ]; then
        echo "✅ Instance created successfully!"
        exit 0
    else
        echo "❌ Failed. Retrying in 60 seconds..."
        sleep 60
    fi
done
