"""Register DSH for this invocation of the upstream command line."""


def main():
    from chi_bench.experiment.agents import registry

    registry.IN_TREE_AGENT_IMPORT_PATHS["dsh"] = "chi_dsh.harbor:DshAgent"
    registry.KNOWN_AGENTS = registry.KNOWN_AGENTS | {"dsh"}
    registry.AGENT_ENV_VARS["dsh"] = ("DEEPSEEK_API_KEY",)
    from chi_bench.cli import app

    app()
