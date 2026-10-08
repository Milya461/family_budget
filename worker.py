from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        result = await self.env.DB.prepare(
            "SELECT value FROM bot_settings WHERE key = 'currency'"
        ).first()

        currency = result["value"] if result else "RUB"

        return Response(
            f"Family Budget bot is starting! Currency: {currency}"
        )
