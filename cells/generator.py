# generator.py

import json
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities


class Generator:
    def __init__(self, host: APIHost):
        """
        Initializes the Generator with the given API host.

        Args:
            host (APIHost): The API host instance.
        """
        self.host = host
        self.ap = host.ap

    async def select_from_list(self, question: str, options: list) -> str:
        """
        Selects the most suitable option from the given list based on the question.

        Args:
            question (str): The question to ask the model.
            options (list): The list of options to choose from.

        Returns:
            str: The selected option.
        """
        model_info = await self.ap.model_mgr.get_model_by_name(
            self.ap.provider_cfg.data["model"]
        )
        prompt = f"""
        Please select the most suitable option from the given list based on the question.
        Question: {question}
        List: {options}
        Ensure your answer contains only one option from the list and no additional explanation or context.
        Model answer:
        """
        response = await model_info.requester.call(
            model=model_info,
            messages=[llm_entities.Message(role="user", content=prompt.strip())],
        )
        return self._clean_response(response.readable_str())

    async def open_ended_question(self, question: str) -> list:
        """
        Asks an open-ended question and returns the answer in JSON list format.

        Args:
            question (str): The open-ended question to ask the model.

        Returns:
            list: The model's answer in JSON list format.
        """
        model_info = await self.ap.model_mgr.get_model_by_name(
            self.ap.provider_cfg.data["model"]
        )
        prompt = f"""
        Please design a list of types based on the question and return the answer in JSON list format.
        Question: {question}
        Ensure your answer is strictly in JSON list format, for example: ['Type1', 'Type2', ...]
        Model answer:
        """
        response = await model_info.requester.call(
            model=model_info,
            messages=[llm_entities.Message(role="user", content=prompt.strip())],
        )
        cleaned_response = self._clean_response(response.readable_str())
        return self._parse_json_list(cleaned_response)

    def _clean_response(self, response: str) -> str:
        """
        Cleans the response by removing role prompts and handling special cases.

        Args:
            response (str): The raw response from the model.

        Returns:
            str: The cleaned response.
        """
        if response.startswith("assistant:"):
            return response[len("assistant: ") :]
        else:
            self.ap.logger.info("Unexpected reply: {}".format(response))
            return "Unexpected reply"

    def _parse_json_list(self, response: str) -> list:
        """
        Parses the response to check if it is a valid JSON list.

        Args:
            response (str): The response from the model.

        Returns:
            list: The parsed list if valid, otherwise an empty list.
        """
        try:
            # Locate the first '[' and the last ']' in the response
            start_index = response.find("[")
            end_index = response.rfind("]") + 1

            # Extract the JSON part of the response
            if start_index != -1 and end_index != -1:
                json_str = response[start_index:end_index]

                # Load the response as JSON
                parsed_list = json.loads(json_str)

                # Check if the parsed object is a list
                if isinstance(parsed_list, list):
                    return parsed_list
                else:
                    self.ap.logger.info("Not a list: {}".format(parsed_list))
                    return []
            else:
                return []
        except json.JSONDecodeError:
            self.ap.logger.info("JSON Decode Error: {}".format(response))
            return []
