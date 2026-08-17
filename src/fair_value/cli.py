import typer
from fair_value.logging_config import configure_logging

from fair_value import __version__


app = typer.Typer(
    name="fair-value",
    help="반도체 기업의 적정가치를 분석하는 데이터 플랫폼",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main() -> None:
    """반도체 기업 가치 분석 CLI."""
    configure_logging()


@app.command()
def version() -> None:
    """현재 프로그램 버전을 출력합니다."""
    typer.echo(__version__)