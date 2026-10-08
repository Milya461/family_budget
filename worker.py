from workers import WorkerEntrypoint, Response


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
            result = await self.env.DB.prepare(
                "SELECT value FROM bot_settings WHERE key = 'currency'"
            ).first()

            currency = result["value"] if result else "RUB"

            return Response(
                f"Family Budget bot is starting! Currency: {currency}"
            )

        except Exception as e:
            return Response(
                f"ERROR: {type(e).__name__}: {e}",
                status=500,
            )
