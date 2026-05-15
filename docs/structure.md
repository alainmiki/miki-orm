# this is how i want the project structure to be

before you start doing anything make sure to first study the django orm like the entire db folder and more like how the top level apis are expose and more. because here. make sure all fields can be accessed with models.FieldName. always validate that code is secure,follows best practices and production ready. db routing,pools and more. the codebase should be clean. makemigration should be able to track diff from models with what is already in the db. migrate and other things that affect the db should be done carefully with backups and rollbacks and atomic. also make sure we have context managers.

imports should be like `from mikiorm.models import Model`  `from mikiorm.manager import BaseManager` or `from mikiorm.bakends import Postgres` etc

### NOTE:
- when restructuring make sure not to try using terminal to write,copy or move files/folders user python.instead so it will be clean and fast for moving,coping and writing files and folders
## top level folder is mikiORM

- `mikiORM/`
  - `conf/`
    - configuration stuffs that gives the user toplevel way to set configuration in their settings that the orm will pickup like the db backend and more.
  - `cli/`
    - In here we handle cli management commands so user can use them like the django cli. expose things like makemigrations, migrate, check, dbcheck,history, roleback commands like in django and more. the cli should be top level so user can just do eg mikiOrm or miki makemigrations etc
  -   `backends/`
        - `base/`
          - base files goes in base folder
        - `sqlite/`
            - sqlite related files goes in here. eg __init__.py sqlite.py,base.py,client.py,creation.py,schema.py operation.py,features.py introspection.py
        - `postgresql/`
            - same as the sqlite files but content specific to sqlite. plus psycopg_any.py,compiler.py etc

        - `mysql/`
          - same file structure as postgresql but content specific to mysql plus it own files
        - `oracle/`
          - same as the postgresql but with it own content and more.
        - `dummy/`
          - dummy database related files and more form inmemory sqlite
    - `migrations/`
        -   `operations/`
         - then other files like in django orm but for mikiORM.

    - `models/`
        - `fields/`
        - `functions/`
        - `sql/`
      - other files like delete.py lookup.py expressions.   query.py options.py aggregates.py constants.py constrains.py etc

    - `managers/`
        - managers related files and folders.
    - `test/`
        -  folder for all test
    - `examples/`
        - real world examples on how to use this orm . real examples that showcase how to user relations,revers relationships, prefetch, select_related and example for crud, blog, social media, e-commerce ,school with class rooms teachers students departments etc
    
  

    - `transactions.py`
    - `utils.py`
    - etc
        