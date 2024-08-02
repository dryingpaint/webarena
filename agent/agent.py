import argparse
import json
from typing import Any
import asyncio

import tiktoken
import time 
from beartype import beartype

from agent.prompts import *
from browser_env import Trajectory
from browser_env.actions import (
    Action,
    ActionParsingError,
    create_id_based_action,
    create_none_action,
    create_playwright_action,
)
from browser_env.utils import Observation, StateInfo
from llms import (
    call_llm,
    generate_from_huggingface_completion,
    generate_from_openai_chat_completion,
    generate_from_openai_completion,
    lm_config,
)
from llms.tokenizers import Tokenizer
from websockets.sync.client import connect
import websockets
from websocket import create_connection
from protos.altera_agents import observations_pb2, actions_pb2
from google.protobuf.struct_pb2 import Struct

import nest_asyncio
nest_asyncio.apply()



class Agent:
    """Base class for the agent"""

    def __init__(self, *args: Any) -> None:
        pass

    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: Any
    ) -> Action:
        """Predict the next action given the observation"""
        raise NotImplementedError

    def reset(
        self,
        test_config_file: str,
    ) -> None:
        raise NotImplementedError


class TeacherForcingAgent(Agent):
    """Agent that follows a pre-defined action sequence"""

    def __init__(self) -> None:
        super().__init__()

    def set_action_set_tag(self, tag: str) -> None:
        self.action_set_tag = tag

    def set_actions(self, action_seq: str | list[str]) -> None:
        if isinstance(action_seq, str):
            action_strs = action_seq.strip().split("\n")
        else:
            action_strs = action_seq
        action_strs = [a.strip() for a in action_strs]

        actions = []
        for a_str in action_strs:
            try:
                if self.action_set_tag == "playwright":
                    cur_action = create_playwright_action(a_str)
                elif self.action_set_tag == "id_accessibility_tree":
                    cur_action = create_id_based_action(a_str)
                else:
                    raise ValueError(
                        f"Unknown action type {self.action_set_tag}"
                    )
            except ActionParsingError as e:
                cur_action = create_none_action()

            cur_action["raw_prediction"] = a_str
            actions.append(cur_action)

        self.actions: list[Action] = actions

    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: Any
    ) -> Action:
        """Predict the next action given the observation"""
        return self.actions.pop(0)

    def reset(
        self,
        test_config_file: str,
    ) -> None:
        with open(test_config_file) as f:
            ref_actions = json.load(f)["reference_action_sequence"]
            tag = ref_actions["action_set_tag"]
            action_seq = ref_actions["action_sequence"]
            self.set_action_set_tag(tag)
            self.set_actions(action_seq)


class PromptAgent(Agent):
    """prompt-based agent that emits action given the history"""

    @beartype
    def __init__(
        self,
        action_set_tag: str,
        lm_config: lm_config.LMConfig,
        prompt_constructor: PromptConstructor,
    ) -> None:
        super().__init__()
        self.lm_config = lm_config
        self.prompt_constructor = prompt_constructor
        self.action_set_tag = action_set_tag

    def set_action_set_tag(self, tag: str) -> None:
        self.action_set_tag = tag

    @beartype
    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: dict[str, Any]
    ) -> Action:
        prompt = self.prompt_constructor.construct(
            trajectory, intent, meta_data
        )
        lm_config = self.lm_config
        n = 0
        while True:
            response = call_llm(lm_config, prompt)
            force_prefix = self.prompt_constructor.instruction[
                "meta_data"
            ].get("force_prefix", "")
            response = f"{force_prefix}{response}"
            n += 1
            try:
                parsed_response = self.prompt_constructor.extract_action(
                    response
                )
                if self.action_set_tag == "id_accessibility_tree":
                    action = create_id_based_action(parsed_response)
                elif self.action_set_tag == "playwright":
                    action = create_playwright_action(parsed_response)
                else:
                    raise ValueError(
                        f"Unknown action type {self.action_set_tag}"
                    )
                action["raw_prediction"] = response
                break
            except ActionParsingError as e:
                if n >= lm_config.gen_config["max_retry"]:
                    action = create_none_action()
                    action["raw_prediction"] = response
                    break

        return action

    def reset(self, test_config_file: str) -> None:
        pass

class AlteraAgent(Agent):

    @beartype
    def __init__(
        self,
        game_env,
        action_space,
        port,
    ) -> None:
        super().__init__()
        self.game_env = game_env
        self.action_space = action_space
        self.action_set_tag = "id_accessibility_tree"
        self.port = f"ws://localhost:{port}"

    def set_action_set_tag(self, tag: str) -> None:
        self.action_set_tag = tag

    def extract_action(self, raw_response: str):
        # pattern = rf"```((.|\n)*?)```"
        # match = re.search(pattern, response)
        # if match:
        #     return match.group(1).strip()
        # else:
        #     raise ActionParsingError(
        #         f'Cannot find the answer phrase "{self.answer_phrase}" in "{response}"'
        #     )
        response = raw_response.split(" ")
        if len(response) > 1:
            if "[" not in response[1]:
                params = f"[{']['.join(response[1:])}]"
            else:
                params = " ".join(response[1:])
            out = f"{response[0]} {params}"
            print(out)
            return out
        else:
            return response[0]

    @beartype
    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: dict[str, Any]
    ) -> Action:
        uri = self.port
        state_info: StateInfo = trajectory[-1] 
        page = state_info["info"]["page"]
        url = page.url
        web_tree = state_info["observation"]["text"]
        
        async def handle_send():
            pass
        
        async def handle_receive():
            pass

        MAX_RETRIES = 10
        RETRY_DELAY = 1

        async def connect():
            for attempt in range(MAX_RETRIES):
                try:
                    return await websockets.connect(uri)
                except Exception as e:
                    print(f"Connection attempt {attempt + 1} failed: {e}")
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(RETRY_DELAY)
            raise Exception("Failed to connect after maximum retries")

        async def async_next_action():
            async def send_message(ws):
                message = observations_pb2.AgentObservation()
                message.agent_id = "webb"
                message.observation_type = observations_pb2.AGENT_OBSERVATION_ENVIRONMENT_INFORMATION
                web_struct = Struct()
                web_struct.update({
                    'url': url,
                    'actionSpace': self.action_space,
                    'gameEnv': self.game_env,
                    'intention': intent,
                    'websiteTree': web_tree,
                })
                message.environment_information.structured_information.CopyFrom(web_struct)
                message_bytes = message.SerializeToString()
                await ws.send(message_bytes)
                print("Message sent!")

            async def receive_message(ws):
                response = await ws.recv()
                print(f"Receiving {response}")
                response_message = actions_pb2.AgentAction()
                response_message.ParseFromString(response)

                if response_message.action_type == actions_pb2.AGENT_ACTION_PERFORM_SKILL:
                    action_response = response_message.perform_skill.message
                    return action_response
                return None

            ws = None
            try:
                ws = await connect()
                await send_message(ws)
                start = time.time()
                while True:
                    try:
                        result = await asyncio.wait_for(receive_message(ws), timeout=5)
                        if result:
                            print(f"Received: {result} after {int(time.time()-start)} s")
                            return result
                    except asyncio.TimeoutError:
                        print(f"Timeout while waiting for response, retrying... Client connection: {ws.open if ws else None}")
                    except websockets.exceptions.ConnectionClosedOK:
                        print(f"Normal connection close. Reconnecting...")
                        ws = await connect()
                        # await send_message(ws)
            finally:
                if ws:
                    await ws.close()
                            
            # except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
            #     print(f"Connection error: {e}. Reconnecting in 0.005 seconds...")
            #     await asyncio.sleep(0.005)

        response = asyncio.get_event_loop().run_until_complete(async_next_action())
        n = 0
        try:
            parsed_response = self.extract_action(
                response
            )
            if self.action_set_tag == "id_accessibility_tree":
                action = create_id_based_action(parsed_response)
            elif self.action_set_tag == "playwright":
                action = create_playwright_action(parsed_response)
            else:
                raise ValueError(
                    f"Unknown action type {self.action_set_tag}"
                )
            action["raw_prediction"] = response
        except ActionParsingError as e:
            action = create_none_action()
            action["raw_prediction"] = response

        print(f"Final action: {action}")
        return action

    def reset(self, test_config_file: str) -> None:
        pass


def construct_agent(args: argparse.Namespace) -> Agent:
    llm_config = lm_config.construct_llm_config(args)

    agent: Agent
    if args.agent_type == "teacher_forcing":
        agent = TeacherForcingAgent()
    elif args.agent_type == "prompt":
        with open(args.instruction_path) as f:
            constructor_type = json.load(f)["meta_data"]["prompt_constructor"]
        tokenizer = Tokenizer(args.provider, args.model)
        prompt_constructor = eval(constructor_type)(
            args.instruction_path, lm_config=llm_config, tokenizer=tokenizer
        )
        agent = PromptAgent(
            action_set_tag=args.action_set_tag,
            lm_config=llm_config,
            prompt_constructor = prompt_constructor,
        )
    elif args.agent_type == "altera":
        with open(args.instruction_path) as f:
            file = json.load(f)
            game_env = file['game_env']
            action_space = file['action_space']
        agent = AlteraAgent(game_env, action_space, args.port)
    else:
        raise NotImplementedError(
            f"agent type {args.agent_type} not implemented"
        )
    return agent
