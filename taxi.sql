SELECT count(*), avg(trip_distance)
FROM 'https://blobs.duckdb.org/data/yellow_tripdata_2010-01.parquet'
WHERE passenger_count > 2;
