from workers import WorkerEntrypoint, Response

from app.db import configure_d1


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        configure_d1(self.env.DB)

        return Response(
            "Family Budget bot is starting!"
        )
