"""
Portfolio service for sharing relevant project photos.
Sends portfolio images when customers ask about specific services.
"""

import structlog
from config import settings

logger = structlog.get_logger()


class PortfolioService:
    """Service for managing and sharing portfolio projects."""

    def __init__(self) -> None:
        self._redis = None
        # Define project types
        self.project_types = ["kitchen", "loft", "bathroom", "full_renovation", "basement"]

    def _get_redis(self):
        """Lazy load Redis connection."""
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.from_url(settings.redis_url)
        return self._redis

    async def find_relevant_projects(
        self,
        project_type: str | None = None,
        postcode_prefix: str | None = None,
        tags: list[str] | None = None,
        limit: int = 3,
    ) -> list[dict]:
        """
        Find portfolio projects matching criteria.

        Args:
            project_type: Type of project (kitchen, loft, etc.)
            postcode_prefix: Postcode area (NW3, NW6, etc.)
            tags: Tags to match (victorian, modern, etc.)
            limit: Maximum projects to return

        Returns:
            List of matching project dictionaries
        """
        redis = self._get_redis()

        # Get all portfolio project keys
        project_keys = await redis.keys("portfolio:project:*")
        projects = []

        for key in project_keys:
            project_data = await redis.hgetall(key)
            if not project_data:
                continue

            # Decode bytes to strings
            project = {k.decode(): v.decode() for k, v in project_data.items()}
            project["id"] = key.decode().split(":")[-1]

            # Filter by project type
            if project_type and project.get("project_type") != project_type:
                continue

            # Filter by postcode prefix
            if postcode_prefix and project.get("postcode_prefix") != postcode_prefix:
                continue

            # Filter by tags (if provided and project has tags)
            if tags:
                project_tags = project.get("tags", "").split(",")
                if not any(tag in project_tags for tag in tags):
                    continue

            # Get associated images
            image_keys = await redis.keys(f"portfolio:image:{project['id']}:*")
            images = []
            for img_key in image_keys:
                img_data = await redis.hgetall(img_key)
                if img_data:
                    img = {k.decode(): v.decode() for k, v in img_data.items()}
                    images.append(img)

            # Sort images by display order
            images.sort(key=lambda x: int(x.get("display_order", 0)))
            project["images"] = images

            projects.append(project)

        # Sort by featured status and completion date
        projects.sort(
            key=lambda x: (x.get("featured", "false") == "true", x.get("completion_date", "")),
            reverse=True,
        )

        return projects[:limit]

    async def get_shareable_images(
        self,
        project_type: str,
        max_images: int = 3,
    ) -> list[dict]:
        """
        Get best images to share via WhatsApp.

        Args:
            project_type: Type of project to show
            max_images: Maximum number of images to return

        Returns:
            List of image dictionaries with url and caption
        """
        projects = await self.find_relevant_projects(project_type=project_type, limit=2)

        images_to_share = []

        for project in projects:
            project_images = project.get("images", [])

            # Prefer 'after' images
            after_images = [img for img in project_images if img.get("image_type") == "after"]

            if after_images:
                images_to_share.append(
                    {
                        "url": after_images[0].get("image_url"),
                        "caption": f"{project.get('title', 'Recent project')} - {after_images[0].get('caption', 'Completed project')}",
                    }
                )
            elif project_images:
                # Fall back to any image
                images_to_share.append(
                    {
                        "url": project_images[0].get("image_url"),
                        "caption": f"{project.get('title', 'Recent project')} - {project_images[0].get('caption', 'Project photo')}",
                    }
                )

            if len(images_to_share) >= max_images:
                break

        logger.info(
            "portfolio_images_retrieved", project_type=project_type, count=len(images_to_share)
        )
        return images_to_share

    async def add_project(
        self,
        title: str,
        project_type: str,
        location: str,
        postcode_prefix: str,
        budget_range: str,
        description: str,
        tags: list[str] | None = None,
        featured: bool = False,
        completion_date: str | None = None,
    ) -> str:
        """
        Add a new portfolio project.

        Args:
            title: Project title
            project_type: Type of project
            location: Area name
            postcode_prefix: Postcode prefix
            budget_range: Budget range string
            description: Project description
            tags: List of tags
            featured: Whether project is featured
            completion_date: Completion date string

        Returns:
            Project ID
        """
        import uuid
        from datetime import datetime

        redis = self._get_redis()
        project_id = str(uuid.uuid4())[:8]

        await redis.hset(
            f"portfolio:project:{project_id}",
            mapping={
                "title": title,
                "project_type": project_type,
                "location": location,
                "postcode_prefix": postcode_prefix,
                "budget_range": budget_range,
                "description": description,
                "tags": ",".join(tags) if tags else "",
                "featured": str(featured).lower(),
                "completion_date": completion_date or datetime.now().strftime("%Y-%m-%d"),
                "created_at": datetime.now().isoformat(),
            },
        )

        logger.info("portfolio_project_added", project_id=project_id, title=title)
        return project_id

    async def add_image(
        self,
        project_id: str,
        image_url: str,
        image_type: str = "after",
        caption: str = "",
        display_order: int = 0,
    ) -> str:
        """
        Add an image to a portfolio project.

        Args:
            project_id: Project ID to add image to
            image_url: S3 or CDN URL of image
            image_type: Type of image (before, after, progress)
            caption: Image caption
            display_order: Display order

        Returns:
            Image ID
        """
        import uuid
        from datetime import datetime

        redis = self._get_redis()
        image_id = str(uuid.uuid4())[:8]

        await redis.hset(
            f"portfolio:image:{project_id}:{image_id}",
            mapping={
                "image_url": image_url,
                "image_type": image_type,
                "caption": caption,
                "display_order": str(display_order),
                "created_at": datetime.now().isoformat(),
            },
        )

        logger.info("portfolio_image_added", project_id=project_id, image_id=image_id)
        return image_id


# Singleton instance
portfolio_service = PortfolioService()
