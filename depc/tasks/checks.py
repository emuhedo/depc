import time

from flask import json
from jinja2.exceptions import TemplateError

from depc.extensions import db, redis
from depc.models.checks import Check
from depc.models.rules import Rule
from depc.sources import BaseSource
from depc.sources.exceptions import UnknownStateException, BadConfigurationException
from depc.tasks import UnrecoverableError
from depc.templates import Template
from depc.utils.qos import compute_qos_from_bools


def merge_all_checks(checks, rule, key, context):
    from depc.tasks.rules import write_log

    result = {"context": context, "logs": []}

    # Remove the result key
    checks_copy = [c["result"] for c in checks]
    result["checks"] = checks_copy

    # Merge the logs
    for check in checks:
        result["logs"].extend(check.pop("logs"))

    # Remove check with no QOS
    checks_copy = [c for c in checks_copy if c["qos"] is not None]

    if checks_copy:
        result_rule = compute_qos_from_bools(
            booleans=[c["bools_dps"] for c in checks_copy]
        )
        result.update(result_rule)

        result["logs"] = write_log(
            result["logs"], "[{0}] Rule done".format(rule.name), "INFO"
        )
        result["logs"] = write_log(
            result["logs"],
            "[{0}] Rule QOS is {1:.5f}%".format(rule.name, result["qos"]),
            "INFO",
        )
    else:
        result["qos"] = "unknown"
        result["logs"] = write_log(
            result["logs"],
            "[{0}] No QOS was found in any checks, so no QOS can be computed for the rule".format(
                rule.name
            ),
            "INFO",
        )

    # Add the check details in the result
    redis.set(
        key, json.dumps(result).encode("utf-8"), ex=redis.seconds_until_midnight()
    )
    result["logs"] = write_log(
        result["logs"],
        "[{0}] Result added in cache ({1})".format(rule.name, key),
        "INFO",
    )

    return result
