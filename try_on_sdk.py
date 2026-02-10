import vertexai
from vertexai.preview.generative_models import GenerativeModel

PROJECT_ID = "project-a250af6f-f898-4bf6-872"
REGION = "us-central1"

vertexai.init(project=PROJECT_ID, location=REGION)

model = GenerativeModel("...")  # model id here
