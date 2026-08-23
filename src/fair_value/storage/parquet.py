from pathlib import Path

import polars as pl


def write_parquet_atomic(frame: pl.DataFrame, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp.parquet")
    frame.write_parquet(temporary, compression="snappy")
    temporary.replace(output_path)
    return output_path
