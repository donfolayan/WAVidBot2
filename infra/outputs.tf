# Outputs - Information displayed after terraform apply

output "instance_public_ip" {
  description = "Public IP address of the instance (FREE, included with Always Free tier)"
  value       = oci_core_instance.wabotii_instance.public_ip
}

output "instance_id" {
  description = "OCID of the compute instance"
  value       = oci_core_instance.wabotii_instance.id
}

output "compartment_id" {
  description = "Compartment OCID (needed for GitHub Actions)"
  value       = var.compartment_id
}

output "ssh_connection" {
  description = "SSH connection command"
  value       = "ssh -i ${local_file.private_key.filename} ubuntu@${oci_core_instance.wabotii_instance.public_ip}"
}

output "ssh_key_location" {
  description = "Location of the private SSH key"
  value       = local_file.private_key.filename
}

output "fastapi_url" {
  description = "FastAPI application URL"
  value       = "http://${oci_core_instance.wabotii_instance.public_ip}:8000"
}

output "waha_dashboard_url" {
  description = "WAHA dashboard URL (scan QR code here)"
  value       = "http://${oci_core_instance.wabotii_instance.public_ip}:3000"
}

output "api_docs_url" {
  description = "FastAPI Swagger documentation"
  value       = "http://${oci_core_instance.wabotii_instance.public_ip}:8000/docs"
}

output "setup_instructions" {
  description = "Next steps after deployment"
  value = <<-EOT
  
  🚀 WABotII Infrastructure Deployed!
  
  📋 NEXT STEPS:
  
  1. Run the setup helper script:
     cd infra
     ./setup-github-secrets.sh
  
  2. Add the 3 secrets to GitHub:
     https://github.com/YOUR_USERNAME/WABotII/settings/secrets/actions
     
     - TERRAFORM_TFVARS
     - OCI_API_KEY
     - ENV_FILE
  
  3. Push to GitHub and watch the magic! ✨
     git add .
     git commit -m "Configure automated deployment"
     git push origin main
  
  The workflow will automatically:
  ✅ Run terraform apply (infrastructure)
  ✅ Deploy your application
  ✅ Start Docker containers
  ✅ Make services available
  
  2. Deploy application via GitHub Actions:
     - Push to main branch, OR
     - Manually trigger: Actions → Deploy to Oracle Cloud → Run workflow
  
  3. After deployment, access your services:
     - WAHA Dashboard: http://${oci_core_instance.wabotii_instance.public_ip}:3000
     - API Docs: http://${oci_core_instance.wabotii_instance.public_ip}:8000/docs
     - Health Check: http://${oci_core_instance.wabotii_instance.public_ip}:8000/health
  
  🔧 Manual SSH access:
     ssh -i ${local_file.private_key.filename} ubuntu@${oci_core_instance.wabotii_instance.public_ip}
  
  💰 Cost: $0/month (Always Free tier)
  🌐 Public IP: ${oci_core_instance.wabotii_instance.public_ip}
  EOT
}
