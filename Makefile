.PHONY: dev build prod logs stop shell-api shell-web test

dev:
	docker compose up

build:
	docker compose build

prod:
	docker compose -f docker-compose.prod.yml up -d

logs:
	docker compose logs -f

stop:
	docker compose down

shell-api:
	docker compose exec api bash

shell-web:
	docker compose exec web sh

test:
	docker compose exec api python -m pytest
