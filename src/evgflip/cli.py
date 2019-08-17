import click


@click.group()
@click.pass_context
def cli(ctx):
    ctx.ensure_object(dict)


def main():
    """Entry point into commandline."""
    return cli(obj={})
