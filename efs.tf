# Persistent job storage mounted at /app/storage in the API (was a PVC / named volume).
resource "aws_efs_file_system" "storage" {
  creation_token   = "${local.name}-storage"
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = { Name = "${local.name}-storage" }
}

resource "aws_efs_backup_policy" "storage" {
  file_system_id = aws_efs_file_system.storage.id

  backup_policy {
    status = "ENABLED"
  }
}

resource "aws_efs_mount_target" "storage" {
  count           = var.az_count
  file_system_id  = aws_efs_file_system.storage.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}

# The API container runs as appuser (uid/gid 1000).
resource "aws_efs_access_point" "storage" {
  file_system_id = aws_efs_file_system.storage.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/storage"
    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0755"
    }
  }
}
