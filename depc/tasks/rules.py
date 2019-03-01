import asyncio
import time
from datetime import datetime

from flask import current_app as app
from jinja2.exceptions import TemplateError

from depc.sources import BaseSource
from depc.sources.exceptions import BadConfigurationException, UnknownStateException
from depc.tasks.checks import merge_all_checks
from depc.templates import Template


def write_log(logs, message, level):
    data = {"created_at": datetime.now(), "message": message, "level": level}
    getattr(app.logger, level.lower())(message)
    logs.append(data)
    return logs


async def execute_asyncio_check(check, name, start, end, key, variables):
    logs = []
    logs = write_log(
        logs, "[{0}] Executing check ({1})...".format(check.name, check.id), "INFO"
    )

    source = check.source
    source_plugin = BaseSource.load_source(source.plugin, source.configuration)
    logs = write_log(
        logs, "[{0}] Raw parameters : {1}".format(check.name, check.parameters), "INFO"
    )

    template = Template(
        check=check,
        context={"name": name, "start": start, "end": end, "variables": variables},
    )

    start_time = time.time()
    error = None
    check_result = None

    try:
        parameters = template.render()
    except TemplateError as e:
        parameters = {}
        error = e
        logs = write_log(logs, "[{0}] {1}".format(check.name, str(error)), "ERROR")
    else:
        logs = write_log(
            logs,
            "[{0}] Rendered parameters : {1}".format(check.name, parameters),
            "DEBUG",
        )

        check_plugin = source_plugin.load_check(
            check_name=check.type,
            parameters=parameters,
            name=name,
            start=start,
            end=end,
        )
        try:
            check_result = await check_plugin.execute()
        except UnknownStateException as e:
            error = e
            logs = write_log(logs, "[{0}] {1}".format(check.name, str(error)), "ERROR")
        except (BadConfigurationException, Exception) as e:
            error = e
            logs = write_log(logs, "[{0}] {1}".format(check.name, str(error)), "ERROR")

    # Display check duration
    duration = time.time() - start_time
    logs = write_log(
        logs, "[{0}] Check duration : {1}s".format(check.name, duration), "INFO"
    )

    result = {
        "id": check.id,
        "name": check.name,
        "type": check.type,
        "parameters": parameters,
        "duration": duration,
        "qos": None,
    }

    if error or not check_result:
        result.update({"error": str(error)})
    else:
        result.update(check_result)

        if result["qos"]:
            logs = write_log(
                logs,
                "[{0}] Check returned {1}%".format(check.name, check_result["qos"]),
                "INFO",
            )
        else:
            logs = write_log(
                logs,
                "[{0}] No QOS returned by the check".format(
                    check.name, check_result["qos"]
                ),
                "INFO",
            )

    return {"logs": logs, "result": result}


async def execute_asyncio_rule(loop, rule, key, kwargs):
    all_checks_result = await asyncio.gather(
        *[
            execute_asyncio_check(
                check=check,
                name=kwargs.get("name"),
                start=kwargs.get("start"),
                end=kwargs.get("end"),
                key=key,
                variables=kwargs.get("variables", {}),
            )
            for check in rule.checks
        ],
        loop=loop,
        return_exceptions=True
    )

    qos = merge_all_checks(checks=all_checks_result, rule=rule, key=key, context=kwargs)

    return qos
