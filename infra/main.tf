resource "oci_core_instance" "Vidbot-Instance" {
    availability_domain = var.availability_domain
    compartment_id = var.compartment_id
}

resource "oci_core_public_ip" "vidbot_ip" {
    compartment_id = var.compartment_id
    lifetime       = "RESERVED"
    display_name   = "vidbot-reserved-ip"
    private_ip_id  = var.private_ip_id
}