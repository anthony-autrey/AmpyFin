# Anthropic Project Guidelines

**Note:** The suggestion_heap feature has been removed as it was using all buying power on trades that were not highly indicated

## Commands
- **Run System**: `docker compose up`
- **Run Setup**: `COMPOSE_PROFILES=setup,mongo docker compose up`
- **Run Training**: `COMPOSE_PROFILES=train,mongo docker compose up`
- **Test**: `python test.py`
- **Health Check**: `python trading_client.py --health`
- **Performance Report**: `python trading_client.py --report`
- **Interactive Container**: `docker exec -it ampyfin-rank /bin/sh`

## Code Style
- **Imports**: Standard library first, third-party second, local imports last
- **Naming**: Snake case for variables/functions (`get_data`), capitalized for indicators (`BBANDS_indicator`)
- **Error Handling**: Specific exceptions with logging, not just print statements
- **Documentation**: Use docstrings for functions and classes
- **Structure**: Keep logic in appropriate directories (strategies/, utils/, helper_files/)
- **Concurrency**: Use semaphores/locks for thread safety
- **Data**: Pandas for manipulation, MongoDB for storage