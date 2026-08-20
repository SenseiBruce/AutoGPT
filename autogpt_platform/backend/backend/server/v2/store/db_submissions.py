"""Store submission, profile, and admin database operations."""

import logging
from datetime import datetime, timezone

import prisma.enums
import prisma.errors
import prisma.models
import prisma.types

import backend.server.v2.store.exceptions
import backend.server.v2.store.model
from backend.util.exceptions import DatabaseError
from backend.util.settings import Settings

logger = logging.getLogger(__name__)
settings = Settings()

DEFAULT_ADMIN_NAME = "AutoGPT Admin"
DEFAULT_ADMIN_EMAIL = "admin@autogpt.co"

async def get_store_submissions(
    user_id: str, page: int = 1, page_size: int = 20
) -> backend.server.v2.store.model.StoreSubmissionsResponse:
    """Get store submissions for the authenticated user -- not an admin"""
    logger.debug(f"Getting store submissions for user {user_id}, page={page}")

    try:
        # Calculate pagination values
        skip = (page - 1) * page_size

        where = prisma.types.StoreSubmissionWhereInput(user_id=user_id)
        # Query submissions from database
        submissions = await prisma.models.StoreSubmission.prisma().find_many(
            where=where,
            skip=skip,
            take=page_size,
            order=[{"date_submitted": "desc"}],
        )

        # Get total count for pagination
        total = await prisma.models.StoreSubmission.prisma().count(where=where)

        total_pages = (total + page_size - 1) // page_size

        # Convert to response models
        submission_models = []
        for sub in submissions:
            submission_model = backend.server.v2.store.model.StoreSubmission(
                agent_id=sub.agent_id,
                agent_version=sub.agent_version,
                name=sub.name,
                sub_heading=sub.sub_heading,
                slug=sub.slug,
                description=sub.description,
                instructions=getattr(sub, "instructions", None),
                image_urls=sub.image_urls or [],
                date_submitted=sub.date_submitted or datetime.now(tz=timezone.utc),
                status=sub.status,
                runs=sub.runs or 0,
                rating=sub.rating or 0.0,
                store_listing_version_id=sub.store_listing_version_id,
                reviewer_id=sub.reviewer_id,
                review_comments=sub.review_comments,
                # internal_comments omitted for regular users
                reviewed_at=sub.reviewed_at,
                changes_summary=sub.changes_summary,
                video_url=sub.video_url,
                categories=sub.categories,
            )
            submission_models.append(submission_model)

        logger.debug(f"Found {len(submission_models)} submissions")
        return backend.server.v2.store.model.StoreSubmissionsResponse(
            submissions=submission_models,
            pagination=backend.server.v2.store.model.Pagination(
                current_page=page,
                total_items=total,
                total_pages=total_pages,
                page_size=page_size,
            ),
        )

    except Exception as e:
        logger.error(f"Error fetching store submissions: {e}")
        # Return empty response rather than exposing internal errors
        return backend.server.v2.store.model.StoreSubmissionsResponse(
            submissions=[],
            pagination=backend.server.v2.store.model.Pagination(
                current_page=page,
                total_items=0,
                total_pages=0,
                page_size=page_size,
            ),
        )


async def delete_store_submission(
    user_id: str,
    submission_id: str,
) -> bool:
    """
    Delete a store listing submission as the submitting user.

    Args:
        user_id: ID of the authenticated user
        submission_id: ID of the submission to be deleted

    Returns:
        bool: True if the submission was successfully deleted, False otherwise
    """
    logger.debug(f"Deleting store submission {submission_id} for user {user_id}")

    try:
        # Verify the submission belongs to this user
        submission = await prisma.models.StoreListing.prisma().find_first(
            where={"agentGraphId": submission_id, "owningUserId": user_id}
        )

        if not submission:
            logger.warning(f"Submission not found for user {user_id}: {submission_id}")
            raise backend.server.v2.store.exceptions.SubmissionNotFoundError(
                f"Submission not found for this user. User ID: {user_id}, Submission ID: {submission_id}"
            )

        # Delete the submission
        await prisma.models.StoreListing.prisma().delete(where={"id": submission.id})

        logger.debug(
            f"Successfully deleted submission {submission_id} for user {user_id}"
        )
        return True

    except Exception as e:
        logger.error(f"Error deleting store submission: {e}")
        return False


async def create_store_submission(
    user_id: str,
    agent_id: str,
    agent_version: int,
    slug: str,
    name: str,
    video_url: str | None = None,
    image_urls: list[str] = [],
    description: str = "",
    instructions: str | None = None,
    sub_heading: str = "",
    categories: list[str] = [],
    changes_summary: str | None = "Initial Submission",
    recommended_schedule_cron: str | None = None,
) -> backend.server.v2.store.model.StoreSubmission:
    """
    Create the first (and only) store listing and thus submission as a normal user

    Args:
        user_id: ID of the authenticated user submitting the listing
        agent_id: ID of the agent being submitted
        agent_version: Version of the agent being submitted
        slug: URL slug for the listing
        name: Name of the agent
        video_url: Optional URL to video demo
        image_urls: List of image URLs for the listing
        description: Description of the agent
        sub_heading: Optional sub-heading for the agent
        categories: List of categories for the agent
        changes_summary: Summary of changes made in this submission

    Returns:
        StoreSubmission: The created store submission
    """
    logger.debug(
        f"Creating store submission for user {user_id}, agent {agent_id} v{agent_version}"
    )

    try:
        # Sanitize slug to only allow letters and hyphens
        slug = "".join(
            c if c.isalpha() or c == "-" or c.isnumeric() else "" for c in slug
        ).lower()

        # First verify the agent belongs to this user
        agent = await prisma.models.AgentGraph.prisma().find_first(
            where=prisma.types.AgentGraphWhereInput(
                id=agent_id, version=agent_version, userId=user_id
            )
        )

        if not agent:
            logger.warning(
                f"Agent not found for user {user_id}: {agent_id} v{agent_version}"
            )
            raise backend.server.v2.store.exceptions.AgentNotFoundError(
                f"Agent not found for this user. User ID: {user_id}, Agent ID: {agent_id}, Version: {agent_version}"
            )

        # Check if listing already exists for this agent
        existing_listing = await prisma.models.StoreListing.prisma().find_first(
            where=prisma.types.StoreListingWhereInput(
                agentGraphId=agent_id, owningUserId=user_id
            )
        )

        if existing_listing is not None:
            logger.info(
                f"Listing already exists for agent {agent_id}, creating new version instead"
            )

            # Delegate to create_store_version which already handles this case correctly
            return await create_store_version(
                user_id=user_id,
                agent_id=agent_id,
                agent_version=agent_version,
                store_listing_id=existing_listing.id,
                name=name,
                video_url=video_url,
                image_urls=image_urls,
                description=description,
                instructions=instructions,
                sub_heading=sub_heading,
                categories=categories,
                changes_summary=changes_summary,
            )

        # If no existing listing, create a new one
        data = prisma.types.StoreListingCreateInput(
            slug=slug,
            agentGraphId=agent_id,
            agentGraphVersion=agent_version,
            owningUserId=user_id,
            createdAt=datetime.now(tz=timezone.utc),
            Versions={
                "create": [
                    prisma.types.StoreListingVersionCreateInput(
                        agentGraphId=agent_id,
                        agentGraphVersion=agent_version,
                        name=name,
                        videoUrl=video_url,
                        imageUrls=image_urls,
                        description=description,
                        instructions=instructions,
                        categories=categories,
                        subHeading=sub_heading,
                        submissionStatus=prisma.enums.SubmissionStatus.PENDING,
                        submittedAt=datetime.now(tz=timezone.utc),
                        changesSummary=changes_summary,
                        recommendedScheduleCron=recommended_schedule_cron,
                    )
                ]
            },
        )
        listing = await prisma.models.StoreListing.prisma().create(
            data=data,
            include=prisma.types.StoreListingInclude(Versions=True),
        )

        store_listing_version_id = (
            listing.Versions[0].id
            if listing.Versions is not None and len(listing.Versions) > 0
            else None
        )

        logger.debug(f"Created store listing for agent {agent_id}")
        # Return submission details
        return backend.server.v2.store.model.StoreSubmission(
            agent_id=agent_id,
            agent_version=agent_version,
            name=name,
            slug=slug,
            sub_heading=sub_heading,
            description=description,
            instructions=instructions,
            image_urls=image_urls,
            date_submitted=listing.createdAt,
            status=prisma.enums.SubmissionStatus.PENDING,
            runs=0,
            rating=0.0,
            store_listing_version_id=store_listing_version_id,
            changes_summary=changes_summary,
        )
    except prisma.errors.UniqueViolationError as exc:
        # Attempt to check if the error was due to the slug field being unique
        error_str = str(exc)
        if "slug" in error_str.lower():
            logger.debug(
                f"Slug '{slug}' is already in use by another agent (agent_id: {agent_id}) for user {user_id}"
            )
            raise backend.server.v2.store.exceptions.SlugAlreadyInUseError(
                f"The URL slug '{slug}' is already in use by another one of your agents. Please choose a different slug."
            ) from exc
        else:
            # Reraise as a generic database error for other unique violations
            raise DatabaseError(
                f"Unique constraint violated (not slug): {error_str}"
            ) from exc
    except (
        backend.server.v2.store.exceptions.AgentNotFoundError,
        backend.server.v2.store.exceptions.ListingExistsError,
    ):
        raise
    except prisma.errors.PrismaError as e:
        logger.error(f"Database error creating store submission: {e}")
        raise DatabaseError("Failed to create store submission") from e


async def edit_store_submission(
    user_id: str,
    store_listing_version_id: str,
    name: str,
    video_url: str | None = None,
    image_urls: list[str] = [],
    description: str = "",
    sub_heading: str = "",
    categories: list[str] = [],
    changes_summary: str | None = "Update submission",
    recommended_schedule_cron: str | None = None,
    instructions: str | None = None,
) -> backend.server.v2.store.model.StoreSubmission:
    """
    Edit an existing store listing submission.

    Args:
        user_id: ID of the authenticated user editing the submission
        store_listing_version_id: ID of the store listing version to edit
        agent_id: ID of the agent being submitted
        agent_version: Version of the agent being submitted
        slug: URL slug for the listing (only changeable for PENDING submissions)
        name: Name of the agent
        video_url: Optional URL to video demo
        image_urls: List of image URLs for the listing
        description: Description of the agent
        sub_heading: Optional sub-heading for the agent
        categories: List of categories for the agent
        changes_summary: Summary of changes made in this submission

    Returns:
        StoreSubmission: The updated store submission

    Raises:
        SubmissionNotFoundError: If the submission is not found
        UnauthorizedError: If the user doesn't own the submission
        InvalidOperationError: If trying to edit a submission that can't be edited
    """
    try:
        # Get the current version and verify ownership
        current_version = await prisma.models.StoreListingVersion.prisma().find_first(
            where=prisma.types.StoreListingVersionWhereInput(
                id=store_listing_version_id
            ),
            include={
                "StoreListing": {
                    "include": {
                        "Versions": {"order_by": {"version": "desc"}, "take": 1}
                    }
                }
            },
        )

        if not current_version:
            raise backend.server.v2.store.exceptions.SubmissionNotFoundError(
                f"Store listing version not found: {store_listing_version_id}"
            )

        # Verify the user owns this submission
        if (
            not current_version.StoreListing
            or current_version.StoreListing.owningUserId != user_id
        ):
            raise backend.server.v2.store.exceptions.UnauthorizedError(
                f"User {user_id} does not own submission {store_listing_version_id}"
            )

        # Currently we are not allowing user to update the agent associated with a submission
        # If we allow it in future, then we need a check here to verify the agent belongs to this user.

        # Check if we can edit this submission
        if current_version.submissionStatus == prisma.enums.SubmissionStatus.REJECTED:
            raise backend.server.v2.store.exceptions.InvalidOperationError(
                "Cannot edit a rejected submission"
            )

        # For APPROVED submissions, we need to create a new version
        if current_version.submissionStatus == prisma.enums.SubmissionStatus.APPROVED:
            # Create a new version for the existing listing
            return await create_store_version(
                user_id=user_id,
                agent_id=current_version.agentGraphId,
                agent_version=current_version.agentGraphVersion,
                store_listing_id=current_version.storeListingId,
                name=name,
                video_url=video_url,
                image_urls=image_urls,
                description=description,
                sub_heading=sub_heading,
                categories=categories,
                changes_summary=changes_summary,
                recommended_schedule_cron=recommended_schedule_cron,
                instructions=instructions,
            )

        # For PENDING submissions, we can update the existing version
        elif current_version.submissionStatus == prisma.enums.SubmissionStatus.PENDING:
            # Update the existing version
            updated_version = await prisma.models.StoreListingVersion.prisma().update(
                where={"id": store_listing_version_id},
                data=prisma.types.StoreListingVersionUpdateInput(
                    name=name,
                    videoUrl=video_url,
                    imageUrls=image_urls,
                    description=description,
                    categories=categories,
                    subHeading=sub_heading,
                    changesSummary=changes_summary,
                    recommendedScheduleCron=recommended_schedule_cron,
                    instructions=instructions,
                ),
            )

            logger.debug(
                f"Updated existing version {store_listing_version_id} for agent {current_version.agentGraphId}"
            )

            if not updated_version:
                raise DatabaseError("Failed to update store listing version")
            return backend.server.v2.store.model.StoreSubmission(
                agent_id=current_version.agentGraphId,
                agent_version=current_version.agentGraphVersion,
                name=name,
                sub_heading=sub_heading,
                slug=current_version.StoreListing.slug,
                description=description,
                instructions=instructions,
                image_urls=image_urls,
                date_submitted=updated_version.submittedAt or updated_version.createdAt,
                status=updated_version.submissionStatus,
                runs=0,
                rating=0.0,
                store_listing_version_id=updated_version.id,
                changes_summary=changes_summary,
                video_url=video_url,
                categories=categories,
                version=updated_version.version,
            )

        else:
            raise backend.server.v2.store.exceptions.InvalidOperationError(
                f"Cannot edit submission with status: {current_version.submissionStatus}"
            )

    except (
        backend.server.v2.store.exceptions.SubmissionNotFoundError,
        backend.server.v2.store.exceptions.UnauthorizedError,
        backend.server.v2.store.exceptions.AgentNotFoundError,
        backend.server.v2.store.exceptions.ListingExistsError,
        backend.server.v2.store.exceptions.InvalidOperationError,
    ):
        raise
    except prisma.errors.PrismaError as e:
        logger.error(f"Database error editing store submission: {e}")
        raise DatabaseError("Failed to edit store submission") from e


async def create_store_version(
    user_id: str,
    agent_id: str,
    agent_version: int,
    store_listing_id: str,
    name: str,
    video_url: str | None = None,
    image_urls: list[str] = [],
    description: str = "",
    instructions: str | None = None,
    sub_heading: str = "",
    categories: list[str] = [],
    changes_summary: str | None = "Initial submission",
    recommended_schedule_cron: str | None = None,
) -> backend.server.v2.store.model.StoreSubmission:
    """
    Create a new version for an existing store listing

    Args:
        user_id: ID of the authenticated user submitting the version
        agent_id: ID of the agent being submitted
        agent_version: Version of the agent being submitted
        store_listing_id: ID of the existing store listing
        name: Name of the agent
        video_url: Optional URL to video demo
        image_urls: List of image URLs for the listing
        description: Description of the agent
        categories: List of categories for the agent
        changes_summary: Summary of changes from the previous version

    Returns:
        StoreSubmission: The created store submission
    """
    logger.debug(
        f"Creating new version for store listing {store_listing_id} for user {user_id}, agent {agent_id} v{agent_version}"
    )

    try:
        # First verify the listing belongs to this user
        listing = await prisma.models.StoreListing.prisma().find_first(
            where=prisma.types.StoreListingWhereInput(
                id=store_listing_id, owningUserId=user_id
            ),
            include={"Versions": {"order_by": {"version": "desc"}, "take": 1}},
        )

        if not listing:
            raise backend.server.v2.store.exceptions.ListingNotFoundError(
                f"Store listing not found. User ID: {user_id}, Listing ID: {store_listing_id}"
            )

        # Verify the agent belongs to this user
        agent = await prisma.models.AgentGraph.prisma().find_first(
            where=prisma.types.AgentGraphWhereInput(
                id=agent_id, version=agent_version, userId=user_id
            )
        )

        if not agent:
            raise backend.server.v2.store.exceptions.AgentNotFoundError(
                f"Agent not found for this user. User ID: {user_id}, Agent ID: {agent_id}, Version: {agent_version}"
            )

        # Get the latest version number
        latest_version = listing.Versions[0] if listing.Versions else None

        next_version = (latest_version.version + 1) if latest_version else 1

        # Create a new version for the existing listing
        new_version = await prisma.models.StoreListingVersion.prisma().create(
            data=prisma.types.StoreListingVersionCreateInput(
                version=next_version,
                agentGraphId=agent_id,
                agentGraphVersion=agent_version,
                name=name,
                videoUrl=video_url,
                imageUrls=image_urls,
                description=description,
                instructions=instructions,
                categories=categories,
                subHeading=sub_heading,
                submissionStatus=prisma.enums.SubmissionStatus.PENDING,
                submittedAt=datetime.now(),
                changesSummary=changes_summary,
                recommendedScheduleCron=recommended_schedule_cron,
                storeListingId=store_listing_id,
            )
        )

        logger.debug(
            f"Created new version for listing {store_listing_id} of agent {agent_id}"
        )
        # Return submission details
        return backend.server.v2.store.model.StoreSubmission(
            agent_id=agent_id,
            agent_version=agent_version,
            name=name,
            slug=listing.slug,
            sub_heading=sub_heading,
            description=description,
            instructions=instructions,
            image_urls=image_urls,
            date_submitted=datetime.now(),
            status=prisma.enums.SubmissionStatus.PENDING,
            runs=0,
            rating=0.0,
            store_listing_version_id=new_version.id,
            changes_summary=changes_summary,
            version=next_version,
        )

    except prisma.errors.PrismaError as e:
        raise DatabaseError("Failed to create new store version") from e


async def create_store_review(
    user_id: str,
    store_listing_version_id: str,
    score: int,
    comments: str | None = None,
) -> backend.server.v2.store.model.StoreReview:
    """Create a review for a store listing as a user to detail their experience"""
    try:
        data = prisma.types.StoreListingReviewUpsertInput(
            update=prisma.types.StoreListingReviewUpdateInput(
                score=score,
                comments=comments,
            ),
            create=prisma.types.StoreListingReviewCreateInput(
                reviewByUserId=user_id,
                storeListingVersionId=store_listing_version_id,
                score=score,
                comments=comments,
            ),
        )
        review = await prisma.models.StoreListingReview.prisma().upsert(
            where={
                "storeListingVersionId_reviewByUserId": {
                    "storeListingVersionId": store_listing_version_id,
                    "reviewByUserId": user_id,
                }
            },
            data=data,
        )

        return backend.server.v2.store.model.StoreReview(
            score=review.score,
            comments=review.comments,
        )

    except prisma.errors.PrismaError as e:
        logger.error(f"Database error creating store review: {e}")
        raise DatabaseError("Failed to create store review") from e
