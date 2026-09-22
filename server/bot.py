import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import HTTPException
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.tts_service import TextAggregationMode
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat_flows import FlowManager
from pipecat_whisker import WhiskerObserver

from flow import create_welcome_node
from models import Order
from order_store import get_order
from tools import MENU_KEYTERMS
from ui_sync import push_order_ui

load_dotenv(Path(__file__).parent / ".env")


async def run_bot(transport):
    logger.info("Starting Food Ordering Agent")

    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        settings=DeepgramSTTService.Settings(
            smart_format=True,
            numerals=True,
            punctuate=True,
            keyterm=MENU_KEYTERMS,
        ),
    )

    google_model = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")
    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(
            model=google_model,
        ),
    )

    tts = DeepgramTTSService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        text_aggregation_mode=TextAggregationMode.TOKEN,
        settings=DeepgramTTSService.Settings(
            voice="aura-asteria-en",
        ),
    )

    rtvi = RTVIProcessor()
    context = LLMContext(messages=[])
    context_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )
    task.add_observer(RTVIObserver(rtvi))
    task.add_observer(WhiskerObserver(task.pipeline, task))

    flow_manager = FlowManager(
        llm=llm,
        context_aggregator=context_aggregator,
        worker=task,
        transport=transport,
    )

    order = Order()
    flow_manager.state["order"] = order
    flow_manager.state["rtvi"] = rtvi

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        await flow_manager.initialize(create_welcome_node())
        await push_order_ui(rtvi, order)

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel(reason="client_disconnected")

    runner = PipelineRunner()
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    if isinstance(runner_args, SmallWebRTCRunnerArguments):
        transport = SmallWebRTCTransport(
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
            webrtc_connection=runner_args.webrtc_connection,
        )
    else:
        logger.error(f"Unsupported runner arguments: {type(runner_args)}")
        return

    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import app, main
    from fastapi.staticfiles import StaticFiles

    @app.get("/api/orders/{order_id}")
    async def fetch_order(order_id: str):
        payload = get_order(order_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Order not found")
        return payload

    try:
        frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"
        if frontend_dir.exists():
            app.mount(
                "/app",
                StaticFiles(directory=str(frontend_dir), html=True),
                name="frontend",
            )
            logger.info("Mounted frontend at http://localhost:7860/app/")
        else:
            logger.warning(
                "frontend/dist not found. Run `npm run build` in frontend/."
            )
    except Exception as e:
        logger.warning(f"Could not mount frontend: {e}")

    main()
