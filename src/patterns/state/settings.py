# Standard Library
import os


def _create_or_update_pyi_files() -> bool:
    create_or_update_pyi_files_raw = os.environ.get(
        'PATTERNS_STATE_CREATE_OR_UPDATE_PYI_FILES', 'false'
    ).lower()

    if create_or_update_pyi_files_raw == 'true':
        return True
    elif create_or_update_pyi_files_raw == 'false':
        return False
    else:
        raise RuntimeError('Env-var not in expected format.')


CREATE_OR_UPDATE_PYI_FILES = _create_or_update_pyi_files()
STATE_CLS_MEMBER_SET_KEY = os.environ.get(
    'PATTERNS_STATE_STATE_CLS_MEMBER_SET_KEY',
    '__patterns_state_pattern_members__',
)
