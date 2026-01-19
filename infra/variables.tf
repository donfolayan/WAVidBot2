# OCI Authentication
variable "tenancy_ocid" {
  description = "OCI Tenancy OCID"
  type        = string
}

variable "user_ocid" {
  description = "OCI User OCID"
  type        = string
}

variable "fingerprint" {
  description = "API Key Fingerprint"
  type        = string
}

variable "private_key_path" {
  description = "Path to private API key"
  type        = string
}

variable "region" {
  description = "OCI Region"
  type        = string
  default     = "us-ashburn-1"
}

# Deployment Configuration
variable "compartment_id" {
  description = "OCI Compartment OCID"
  type        = string
}

variable "availability_domain" {
  description = "Availability Domain (e.g., 'aBCD:US-ASHBURN-AD-1')"
  type        = string
}

# Instance Configuration
variable "instance_shape" {
  description = "Instance shape (e.g., 'VM.Standard.E2.1.Micro' for free tier)"
  type        = string
  default     = "VM.Standard.E2.1.Micro"
}

variable "instance_ocpus" {
  description = "Number of OCPUs for flexible shapes"
  type        = number
  default     = 1
}

variable "instance_memory_gb" {
  description = "Memory in GB for flexible shapes"
  type        = number
  default     = 6
}

variable "image_id" {
  description = "OCID of the OS image (Ubuntu, Oracle Linux, etc.)"
  type        = string
}

# Application Configuration
variable "github_repo" {
  description = "GitHub repository URL (e.g., 'https://github.com/user/WABotII.git')"
  type        = string
}

variable "base_url" {
  description = "Base URL for the application (will use reserved IP if not provided)"
  type        = string
  default     = ""
}

# WAHA Configuration
variable "waha_api_key" {
  description = "WAHA API Key"
  type        = string
  sensitive   = true
}

variable "waha_dashboard_username" {
  description = "WAHA Dashboard Username"
  type        = string
  default     = "admin"
}

variable "waha_dashboard_password" {
  description = "WAHA Dashboard Password"
  type        = string
  sensitive   = true
}

variable "whatsapp_swagger_username" {
  description = "WhatsApp Swagger Username"
  type        = string
  default     = "admin"
}

variable "whatsapp_swagger_password" {
  description = "WhatsApp Swagger Password"
  type        = string
  sensitive   = true
}

# Cloudinary Configuration
variable "cloudinary_cloud_name" {
  description = "Cloudinary Cloud Name"
  type        = string
}

variable "cloudinary_api_key" {
  description = "Cloudinary API Key"
  type        = string
  sensitive   = true
}

variable "cloudinary_api_secret" {
  description = "Cloudinary API Secret"
  type        = string
  sensitive   = true
}