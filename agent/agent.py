import argparse
import json
from typing import Any
import asyncio

import tiktoken
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
    ) -> None:
        super().__init__()
        self.game_env = game_env
        self.action_space = action_space

    def set_action_set_tag(self, tag: str) -> None:
        self.action_set_tag = tag

    @beartype
    def next_action(
        self, trajectory: Trajectory, intent: str, meta_data: dict[str, Any]
    ) -> Action:
        uri = "ws://localhost:8765"
        state_info: StateInfo = trajectory[-1] 
        page = state_info["info"]["page"]
        url = page.url
        web_tree = state_info["observation"]["text"]
        async def async_next_action():
            while True:
                try:
                    async with websockets.connect(uri) as websocket:
                        # Create a Protobuf message
                        message = observations_pb2.AgentObservation()
                        message.agent_id = "webb"
                        message.observation_type = observations_pb2.AGENT_OBSERVATION_ENVIRONMENT_INFORMATION
                        web_struct = Struct()
                        web_struct.update({'url': "www.google.com"})
                        web_struct['action_space'] = self.action_space
                        web_struct['game_env'] = self.game_env
                        web_struct['intention'] = intent
                        web_struct['website_tree'] = web_tree
                        message.environment_information.structured_information.CopyFrom(web_struct)
                        # Serialize the message to binary
                        print(f"Sending \n {message}")
                        message_bytes = message.SerializeToString()
                        # Send the message
                        await websocket.send(message_bytes)
                        while True:
                            # Receive a response (if expected)
                            response = await websocket.recv()
                            print(f"Response: {response}")

                            # Deserialize the received message
                            response_message = actions_pb2.AgentAction()
                            response_message.ParseFromString(response)

                            if response_message.action_type == actions_pb2.AGENT_ACTION_PERFORM_SKILL:
                                action_response = response_message.perform_skill.message
                                print(f"Received: {action_response}")
                                return action_response
                except (websockets.ConnectionClosedError, websockets.InvalidURI, websockets.InvalidHandshake) as e:
                    print(f"Connection error: {e}. Reconnecting in {SLEEP} seconds...")
                    await asyncio.sleep(SLEEP)

        response = asyncio.get_event_loop().run_until_complete(async_next_action())
        return response

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
        agent = AlteraAgent(game_env, action_space)
    else:
        raise NotImplementedError(
            f"agent type {args.agent_type} not implemented"
        )
    return agent
