# GAS Framework
An enhanced web framework (based on [Flask](https://flask.palletsprojects.com/)) for use in the capstone project. Adds robust user authentication (via [Globus Auth](https://docs.globus.org/api/auth)), modular templates, and some simple styling based on [Bootstrap](https://getbootstrap.com/docs/3.3/).

Directory contents are as follows:
* `/web` - The GAS web app files
* `/ann` - Annotator files
* `/util` - Utility scripts/apps for notifications, archival, and restoration
* `/aws` - AWS user data files

### Sequence of events along with where they are handled:
![Alt text](image.png)

### Notes on Data Restoration:
1. Using Lambda instead of directly triggering SNS: I did this to decouple the glacier-thawing job process from the restoration process. This architecture is more scalable than directly triggering SNS after the thawing process.

2. Using just SNS for Lambda vs. SQS-SNS: Although I used only SNS to process thaw requests, it seems like using SQS along with lambda would have been a better design choice. One issue I faced, for example, was an inability to track incomplete jobs or the sequence of jobs. All of them seem to be done, but if I had some more time, I would figure out a way to track/monitor and think more deeply about queing of messages. Source: https://repost.aws/questions/QURliL5lCbQseTNfFiION8nA/sns-to-lambda-vs-sns-to-sqs-to-lambda. 

3. More on tracking: For tracking, I also thought about adding more columns to dynamo; for example, time when an update was made to 'results_file' using the thawed_object but I did not implement anything new. Would appreciate feedback / guidance on how to ensure only messages that are processed completely are deleted ensuring everything is processed, and processed only once.