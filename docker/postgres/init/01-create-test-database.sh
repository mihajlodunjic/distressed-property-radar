#!/bin/bash
set -e

TEST_DB="${POSTGRES_TEST_DB:-distressed_property_radar_test}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE "$TEST_DB";
EOSQL
