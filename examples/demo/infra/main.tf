resource "aws_instance" "backend" {
  ami                    = "ami-0123456789abcdef0"
  instance_type          = "t3.small"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]

  tags = {
    Role = "backend"
  }
}

resource "aws_instance" "edge" {
  ami                    = "ami-0123456789abcdef0"
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.web.id]

  depends_on = [aws_instance.backend]
}

module "frontend_assets" {
  source    = "./modules/assets"
  origin_id = aws_instance.edge.id
}

output "backend_ip" {
  value = aws_instance.backend.id
}

output "assets_domain" {
  value = module.frontend_assets.domain
}
