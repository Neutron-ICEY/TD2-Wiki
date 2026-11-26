"""Deployment boundary. The only implemented publisher is offline MANUAL."""

from pathlib import Path

from .bundle import verify_bundle


class ManualPublisher:
    def prepare(self, bundle: Path) -> str:
        verify_bundle(bundle)
        return (bundle / "publish-report.md").read_text(encoding="utf-8")

    def publish(self, bundle: Path, approved_plan: Path) -> None:
        raise RuntimeError("MANUAL 模式仅导出审核包；请人工发布到 HuijiWiki。")
