# Generate SSH key pair for instance access
resource "tls_private_key" "ssh_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# Save private key locally
resource "local_file" "private_key" {
  content         = tls_private_key.ssh_key.private_key_pem
  filename        = "${path.module}/wabotii-ssh-key.pem"
  file_permission = "0600"
}

# VCN (Virtual Cloud Network)
resource "oci_core_vcn" "wabotii_vcn" {
  compartment_id = var.compartment_id
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "wabotii-vcn"
  dns_label      = "wabotii"
}

# Internet Gateway
resource "oci_core_internet_gateway" "wabotii_igw" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.wabotii_vcn.id
  display_name   = "wabotii-igw"
  enabled        = true
}

# Route Table
resource "oci_core_route_table" "wabotii_route_table" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.wabotii_vcn.id
  display_name   = "wabotii-route-table"

  route_rules {
    network_entity_id = oci_core_internet_gateway.wabotii_igw.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
}

# Security List
resource "oci_core_security_list" "wabotii_security_list" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.wabotii_vcn.id
  display_name   = "wabotii-security-list"

  # Egress - Allow all outbound
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    stateless   = false
  }

  # Ingress - SSH
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 22
      max = 22
    }
  }

  # Ingress - HTTP
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 80
      max = 80
    }
  }

  # Ingress - HTTPS
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 443
      max = 443
    }
  }

  # Ingress - FastAPI (8000)
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 8000
      max = 8000
    }
  }

  # Ingress - WAHA (3000)
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false

    tcp_options {
      min = 3000
      max = 3000
    }
  }
}

# Subnet
resource "oci_core_subnet" "wabotii_subnet" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.wabotii_vcn.id
  cidr_block        = "10.0.1.0/24"
  display_name      = "wabotii-subnet"
  dns_label         = "wabotiisubnet"
  route_table_id    = oci_core_route_table.wabotii_route_table.id
  security_list_ids = [oci_core_security_list.wabotii_security_list.id]
}

# Compute Instance
resource "oci_core_instance" "wabotii_instance" {
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_id
  shape               = var.instance_shape
  display_name        = "wabotii-instance"

  # Shape config for flexible shapes (adjust if needed)
  dynamic "shape_config" {
    for_each = length(regexall("Flex", var.instance_shape)) > 0 ? [1] : []
    content {
      ocpus         = var.instance_ocpus
      memory_in_gbs = var.instance_memory_gb
    }
  }

  # OS Image
  source_details {
    source_type = "image"
    source_id   = var.image_id
  }

  # Network configuration
  create_vnic_details {
    subnet_id        = oci_core_subnet.wabotii_subnet.id
    display_name     = "wabotii-vnic"
    assign_public_ip = true # Free public IP included with instance
    hostname_label   = "wabotii"
  }

  # SSH key and startup script
  metadata = {
    ssh_authorized_keys = tls_private_key.ssh_key.public_key_openssh
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }

  preserve_boot_volume = false

  lifecycle {
    create_before_destroy = false
  }
}

# Public IP is assigned directly to the instance via VNIC
# This is FREE and included with the Always Free tier VM.Standard.E2.1.Micro instance
# The IP will be assigned automatically and available via instance.public_ip