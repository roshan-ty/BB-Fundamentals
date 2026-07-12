#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - Pipeline Coordinator
Orchestrates the execution of all data pipeline scripts in the correct order.
Manages dependencies between fetch scripts and the analysis engine.
"""

import os
import sys
import subprocess
import logging
import time
from datetime import datetime, timezone
from typing import List, Tuple

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Pipeline Stage Definitions
# ---------------------------------------------------------------------------

class PipelineStage:
    """Represents a single stage in the data pipeline."""
    
    def __init__(self, name: str, script_name: str, required: bool = True):
        self.name = name
        self.script_path = os.path.join(SCRIPTS_DIR, script_name)
        self.required = required

    def run(self) -> bool:
        """Execute the stage script. Returns True on success, False on failure."""
        if not os.path.exists(self.script_path):
            logger.error(f"Script not found: {self.script_path}")
            return False

        logger.info(f"+" + "=" * 58)
        logger.info(f"  Running Stage: {self.name}")
        logger.info(f"  Script: {self.script_name}")
        logger.info(f"+" + "=" * 58)

        start_time = time.time()
        try:
            result = subprocess.run(
                [sys.executable, self.script_path],
                capture_output=False,
                check=False,
            )
            elapsed = time.time() - start_time

            if result.returncode == 0:
                logger.info(f"  Stage '{self.name}' completed successfully in {elapsed:.2f}s")
                return True
            else:
                logger.error(f"  Stage '{self.name}' FAILED (exit code {result.returncode}) in {elapsed:.2f}s")
                if result.stderr:
                    logger.error(f"  STDERR: {result.stderr.decode('utf-8', errors='replace')}")
                return False

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"  Stage '{self.name}' raised an exception after {elapsed:.2f}s: {e}")
            return False

    @property
    def script_name(self) -> str:
        return os.path.basename(self.script_path)


# ---------------------------------------------------------------------------
# Pipeline Definitions
# ---------------------------------------------------------------------------

def build_full_pipeline() -> List[PipelineStage]:
    """
    Build the full pipeline that runs every 30-60 minutes.
    Order: macro -> cftc -> yfinance -> analysis_engine
    """
    return [
        PipelineStage(
            "FRED Macro Data Fetch",
            "fetch_macro.py",
            required=True,
        ),
        PipelineStage(
            "CFTC Commitment of Traders Data Fetch",
            "fetch_cftc.py",
            required=True,
        ),
        PipelineStage(
            "Yahoo Finance Market Prices Fetch",
            "fetch_yfinance.py",
            required=True,
        ),
        PipelineStage(
            "Quantitative Institutional Analysis Engine",
            "analysis_engine.py",
            required=True,
        ),
    ]


def build_high_frequency_pipeline() -> List[PipelineStage]:
    """
    Build the high-frequency pipeline that runs every 5-15 minutes.
    Order: calendar -> news
    """
    return [
        PipelineStage(
            "Economic Calendar Data Fetch",
            "fetch_calendar.py",
            required=False,
        ),
        PipelineStage(
            "Live News Feed Data Fetch",
            "fetch_news.py",
            required=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Pipeline Executor
# ---------------------------------------------------------------------------

def run_pipeline(stages: List[PipelineStage], pipeline_name: str) -> int:
    """
    Execute a sequence of pipeline stages.
    Returns 0 if all required stages succeeded, 1 if any required stage failed.
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"  Bulls & Bears Fundamentals - Pipeline: {pipeline_name}")
    logger.info(f"  Started at: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)
    logger.info("")

    total_stages = len(stages)
    success_count = 0
    failure_count = 0

    for i, stage in enumerate(stages, 1):
        logger.info(f"  [{i}/{total_stages}] Processing stage: {stage.name}")
        
        success = stage.run()
        
        if success:
            success_count += 1
        else:
            failure_count += 1
            if stage.required:
                logger.error(f"  CRITICAL: Required stage '{stage.name}' failed. Aborting pipeline.")
                return 1
            else:
                logger.warning(f"  Non-required stage '{stage.name}' failed. Continuing...")
        
        logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info(f"  Pipeline '{pipeline_name}' Summary")
    logger.info(f"  Total Stages: {total_stages}")
    logger.info(f"  Successful: {success_count}")
    logger.info(f"  Failed: {failure_count}")
    logger.info(f"  Completed at: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    return 0


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Main entry point for the pipeline coordinator.
    Determines which pipeline to run based on command-line arguments or environment.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Bulls & Bears Fundamentals - Data Pipeline Coordinator"
    )
    parser.add_argument(
        "--pipeline",
        type=str,
        choices=["full", "high-frequency", "both"],
        default="full",
        help="Which pipeline to execute (default: full)",
    )

    args = parser.parse_args()

    if args.pipeline == "full":
        stages = build_full_pipeline()
        exit_code = run_pipeline(stages, "Full Pipeline (30-60 min cycle)")
    elif args.pipeline == "high-frequency":
        stages = build_high_frequency_pipeline()
        exit_code = run_pipeline(stages, "High-Frequency Pipeline (5-15 min cycle)")
    elif args.pipeline == "both":
        # Run full pipeline first, then high-frequency
        full_stages = build_full_pipeline()
        exit_code = run_pipeline(full_stages, "Full Pipeline (30-60 min cycle)")
        
        if exit_code == 0:
            hf_stages = build_high_frequency_pipeline()
            exit_code = run_pipeline(hf_stages, "High-Frequency Pipeline (5-15 min cycle)")
    else:
        logger.error(f"Unknown pipeline type: {args.pipeline}")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()