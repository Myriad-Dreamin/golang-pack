import re

from config import LoaderConfig, ModuleConfig, ParseConfig, GolangPackConfig
from golang_pack import GolangPack
from loader.stub import StubLoader

if __name__ == '__main__':
    GolangPack.register_loader('stub-loader', StubLoader)

    golang_pack = GolangPack(GolangPackConfig(
        name='boj-v6',
        version='v0.5.0',
        description='golang pack test config',
        local_toolset='..',
        local_package='F:/work/boj-v6',
        src='cmd/generate/model',
        output='app/generated_controller',
        module=ModuleConfig(
            loaders=[
                LoaderConfig(test=re.compile(r'.*?.stub.go$'), target='[file-name].gen.go', use='stub-loader'),
            ]
        ),
        parse=ParseConfig(
            force_update=True,
        ),
    ))

    golang_pack.once()
