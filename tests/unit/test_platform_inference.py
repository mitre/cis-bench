"""Unit tests for platform inference from benchmark titles."""

from cis_bench.catalog.parser import WorkBenchCatalogParser


class TestPlatformInference:
    """Test platform type and name inference from titles."""

    # Operating Systems
    def test_ubuntu_inference(self):
        """Infer Ubuntu platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Ubuntu Linux 22.04 Benchmark"
        )
        assert platform_type == "os"
        assert platform == "ubuntu"

    def test_almalinux_inference(self):
        """Infer AlmaLinux platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS AlmaLinux OS 8 Benchmark"
        )
        assert platform_type == "os"
        assert platform == "almalinux"

    def test_rhel_inference(self):
        """Infer Red Hat platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Red Hat Enterprise Linux 9 Benchmark"
        )
        assert platform_type == "os"
        assert platform == "red-hat"

    def test_windows_server_inference(self):
        """Infer Windows Server platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Microsoft Windows Server 2022 Benchmark"
        )
        assert platform_type == "os"
        assert platform == "windows-server"

    def test_macos_inference(self):
        """Infer macOS platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Apple macOS 14.0 Sonoma Benchmark"
        )
        assert platform_type == "os"
        assert platform == "macos"

    # Cloud Platforms
    def test_aws_inference(self):
        """Infer AWS platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Amazon Web Services Foundations Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "aws"

    def test_azure_inference(self):
        """Infer Azure platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Microsoft Azure Foundations Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "azure"

    def test_google_cloud_inference(self):
        """Infer Google Cloud platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Google Cloud Platform Foundation Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "google-cloud"

    def test_oracle_cloud_inference(self):
        """Infer Oracle Cloud platform (not Oracle DB)."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Cloud Infrastructure Foundations Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "oracle-cloud"

    def test_alibaba_cloud_inference(self):
        """Infer Alibaba Cloud platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Alibaba Cloud Foundation Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "alibaba-cloud"

    # Databases
    def test_oracle_database_inference(self):
        """Infer Oracle Database platform (not Oracle Cloud)."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Database 19c Benchmark"
        )
        assert platform_type == "database"
        assert platform == "oracle-database"

    def test_mysql_inference(self):
        """Infer MySQL platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle MySQL Enterprise Edition 8.0 Benchmark"
        )
        assert platform_type == "database"
        assert platform == "mysql"

    def test_postgresql_inference(self):
        """Infer PostgreSQL platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS PostgreSQL 15 Benchmark"
        )
        assert platform_type == "database"
        assert platform == "postgresql"

    # Containers & Kubernetes
    def test_kubernetes_inference(self):
        """Infer Kubernetes platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Kubernetes V1.28 Benchmark"
        )
        assert platform_type == "container"
        assert platform == "kubernetes"

    def test_docker_inference(self):
        """Infer Docker platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform("CIS Docker Benchmark")
        assert platform_type == "container"
        assert platform == "docker"

    def test_eks_inference(self):
        """Infer AWS EKS platform."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark"
        )
        assert platform_type == "container"
        assert platform == "aws-eks"

    def test_aks_inference(self):
        """Infer Azure AKS platform (categorized as cloud since it's Azure service)."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Azure Kubernetes Service (AKS) Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "azure"

    def test_oke_inference(self):
        """Infer Oracle OKE platform (categorized as cloud since it's Oracle Cloud service)."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Cloud Infrastructure Container Engine for Kubernetes(OKE) Benchmark"
        )
        assert platform_type == "cloud"
        assert platform == "oracle-cloud"

    # Edge Cases
    def test_no_match_returns_none(self):
        """Unknown platform returns (None, None)."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Unknown Platform Benchmark"
        )
        assert platform_type is None
        assert platform is None

    def test_oracle_linux_not_oracle_cloud(self):
        """Oracle Linux is OS, not cloud (order matters)."""
        platform_type, platform = WorkBenchCatalogParser._infer_platform(
            "CIS Oracle Linux 8 Benchmark"
        )
        assert platform_type == "os"
        assert platform == "oracle-linux"
