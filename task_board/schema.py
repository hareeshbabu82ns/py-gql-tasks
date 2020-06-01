# schema.py
import datetime
from ariadne import QueryType, MutationType, make_executable_schema, ObjectType, snake_case_fallback_resolvers
from ariadne.contrib.django.scalars import date_scalar, datetime_scalar
from django.db import transaction
from django.db.models import F, Q, Max

from tasks.models import Board, TaskLane, Task, User

type_defs = """
    scalar Date
    scalar DateTime

    type Mutation {
        moveTask(id:ID!,toLane:ID,toItemOrder:Int!):Task!
        moveLane(id:ID!,toLaneOrder:Int!):TaskLane!
        createTask(input:TaskCreateInput!):Task!
        updateTask(id:ID!,input:TaskUpdateInput!):Task!
        deleteTask(id:ID!):Boolean!
    }

    type Query {
        boards(id:ID,title:String): [Board!]
        lanes(id:ID,title:String,board:ID,forUser:ID): [TaskLane!]
        tasks(id:ID,title:String,forUser:ID,board:ID,lane:ID): [Task!]
        users(id:ID,name:String):[User!]
        searchTasks(board:ID!,text:String!):[Task!]
    }
    type Board {
      id : ID!
      title : String!
      lanes: [TaskLane!]
    }
    type TaskLane {
        id: ID!
        board: Board
        order: Int
        title: String!
        tasks(searchQuery:String): [Task!]
    }
    type Task {
        id: ID!
        board: Board!
        lane: TaskLane!
        order: Int
        title: String!
        description: String
        assignedTo: User!
        dueBy: DateTime
    }
    type User {
        id: ID!
        name: String!
        avatar: String
        tasks(lane:ID,board:ID):[Task!]
    }

    input TaskCreateInput {
        laneId: ID!
        boardId: ID
        order: Int
        title: String!
        description: String
        assignedTo: ID!
        dueBy: DateTime
        tags: String
    }    

    input TaskUpdateInput {
        laneId: ID
        boardId: ID
        order: Int
        title: String
        description: String
        assignedTo: ID
        dueBy: DateTime
        tags: String
    }        
"""

mutation = MutationType()


@mutation.field('deleteTask')
def resolve_delete_task(*_, id):
    task = Task.objects.get(id=id)
    task.delete()
    return True


@mutation.field('updateTask')
def resolve_update_task(*_, id, input):

    task = Task.objects.get(id=id)
    lane = task.lane_id
    fromLane = task.lane_id.id
    fromOrder = task.order
    toLane = fromLane
    toOrder = fromOrder

    if input.get('title'):
        task.title = input.get('title')
    if input.get('description'):
        task.description = input.get('description')
    if input.get('dueBy'):
        task.due_by = input.get('dueBy')

    if input.get('laneId') and task.lane_id.id != input.get('laneId'):  # moving to different lane
        lane = TaskLane.objects.get(id=input.get('laneId'))
        task.lane_id = lane
        toLane = lane.id
        if not input.get('order'):  # order not provided for new lane, move as last item
            task.order = lane.task_set.aggregate(
                Max('order'))['order__max'] + 1
            toOrder = task.order

    if input.get('assignedTo') and task.assigned_to.id != input.get('assignedTo'):
        user = User.objects.get(id=input.get('assignedTo'))
        task.assigned_to = user

    if input.get('order'):
        task.order = input.get('order')
        toOrder = task.order
        if not input.get('laneId'):
            toLane = lane.id

    try:
        with transaction.atomic():
            task.save()
            if fromLane != toLane or fromOrder != toOrder:
                update_task_order(task, lane, fromLane,
                                  fromOrder, toLane, toOrder)

        return task
    except Exception as ex:
        print(ex)
        raise Exception(f'Task updation failed: ${ex}')


@mutation.field('createTask')
def resolve_create_task(*_, input):
    taskInput = {
        "order": input.get("order") if input.get("order") else 0,
        "title": input["title"],
        "description": input.get("description"),
        'due_by': input.get('dueBy'),
    }

    if not input.get('dueBy'):
        taskInput['due_by'] = datetime.datetime.now()

    lane = TaskLane.objects.get(id=input["laneId"])
    user = User.objects.get(id=input['assignedTo'])

    try:
        with transaction.atomic():
            task = Task(**taskInput)
            task.board_id = lane.board_id
            task.lane_id = lane
            task.assigned_to = user

            if not taskInput["order"]:
                task.order = lane.task_set.aggregate(
                    Max('order'))['order__max'] + 1

            task.save()

            # update destination lane
            if taskInput["order"]:
                updatedTasks = Task.objects.filter(lane_id=lane.id).filter(order__gte=task.order).exclude(
                    id=task.id).update(order=F('order')+1)

        return task
    except Exception as ex:
        print(ex)
        raise Exception(f'Task creation failed: ${ex}')


@mutation.field('moveLane')
def resolve_move_lane(*_, id=None, toLaneOrder=None):
    lane = TaskLane.objects.get(id=id)

    if lane.order == toLaneOrder:
        # nothing to update, same position
        return lane

    fromLaneOrder = lane.order

    if toLaneOrder:
        lane.order = toLaneOrder
    else:
        raise Exception('Destination Lane missing')

    laneStep = toLaneOrder - fromLaneOrder

    with transaction.atomic():
        lane.save()

        # move order for other tasks in the destination lane
        updatedTasks = TaskLane.objects

        if laneStep > 0:
            updatedTasks = updatedTasks.filter(order__range=(
                fromLaneOrder+1, toLaneOrder)).exclude(id=lane.id).update(order=F('order')-1)
        else:
            updatedTasks = updatedTasks.filter(order__range=(
                toLaneOrder, fromLaneOrder-1)).exclude(id=lane.id).update(order=F('order')+1)

    return lane


@mutation.field('moveTask')
def resolve_move_task(*_, id=None, toLane=None, toItemOrder=None):
    task = Task.objects.get(id=id)

    lane = task.lane_id

    if lane.id == toLane and task.order == toItemOrder:
        # no change is needed
        return task

    fromLane = lane.id
    if toLane and lane.id != toLane:
        lane = TaskLane.objects.get(id=toLane)
        task.lane_id = lane

    toLane = lane.id

    fromItemOrder = task.order
    if toItemOrder:
        task.order = toItemOrder
    else:
        raise Exception('Destination Item Order missing')

    with transaction.atomic():
        task.save()

    # move order for other tasks in the destination lane
        update_task_order(task, lane, fromLane,
                          fromItemOrder, toLane, toItemOrder)
        # if fromLane != toLane:
        #     # update destination lane
        #     updatedTasks = lane.task_set.filter(order__gte=toItemOrder).exclude(
        #         id=task.id).update(order=F('order')+1)
        #     # update source lane
        #     updatedTasks = Task.objects.filter(lane_id=fromLane, order__gte=fromItemOrder).exclude(
        #         id=task.id).update(order=F('order')-1)
        # else:
        #     taskStep = toItemOrder - fromItemOrder
        #     print(taskStep)
        #     if taskStep > 0:
        #         updatedTasks = lane.task_set.filter(order__range=(
        #             fromItemOrder+1, toItemOrder)).exclude(
        #             id=task.id).update(order=F('order')-1)
        #     else:
        #         updatedTasks = lane.task_set.filter(order__range=(
        #             toItemOrder, fromItemOrder-1)).exclude(
        #             id=task.id).update(order=F('order')+1)

    return task


def update_task_order(task, destinationLane, fromLane, fromOrder, toLane, toOrder):
    if not destinationLane:
        destinationLane = TaskLane.objects.get(id=toLane)
    # move order for other tasks in the destination lane
    if fromLane != toLane:
        # update destination lane
        updatedTasks = destinationLane.task_set.filter(order__gte=toOrder).exclude(
            id=task.id).update(order=F('order')+1)
        # update source lane
        updatedTasks = Task.objects.filter(lane_id=fromLane, order__gte=fromOrder).exclude(
            id=task.id).update(order=F('order')-1)
    else:
        taskStep = toOrder - fromOrder
        print(taskStep)
        if taskStep > 0:
            updatedTasks = destinationLane.task_set.filter(order__range=(
                fromOrder+1, toOrder)).exclude(
                id=task.id).update(order=F('order')-1)
        else:
            updatedTasks = destinationLane.task_set.filter(order__range=(
                toOrder, fromOrder-1)).exclude(
                id=task.id).update(order=F('order')+1)


query = QueryType()


@query.field('searchTasks')
def resolve_search_tasks(*_, board=None, text=None):
    q = Task.objects
    if board == None or text == None:
        raise Exception('missing arguments for search...')

    if len(text) < 5:
        raise Exception('search string empty or too short')

    q = q.filter(Q(board_id=board), Q(title__contains=text)
                 | Q(description__contains=text))

    return q


@query.field('users')
def resolve_boards(*_, id=None, name=None):
    q = User.objects
    if id:
        q = q.filter(id=id)
    if name:
        q = q.filter(name__contains=name)

    if not(id and name):
        q = q.all()

    return q


@query.field('boards')
def resolve_boards(*_, id=None, title=None):
    q = Board.objects
    if id:
        q = q.filter(id=id)
    if title:
        q = q.filter(title__contains=title)

    if not(id and title):
        q = q.all()

    return q


@query.field('lanes')
def resolve_lanes(*_, id=None, title=None, board=None, forUser=None):
    q = TaskLane.objects

    if id:
        q = q.filter(id=id)

    if title:
        q = q.filter(title__contains=title)
    if board:
        q = q.filter(board_id=board)
    if forUser:
        q = q.filter(task__assigned_to=forUser)

    return q.order_by('order')


@query.field('tasks')
def resolve_tasks(*_, id=None, title=None, forUser=None, board=None, lane=None):
    if id:
        return [Task.objects.get(id=id)]

    q = Task.objects
    if title:
        q = q.filter(title__contains=title)

    if forUser:
        q = q.filter(assigned_to=forUser)
    if board:
        q = q.filter(board_id=board)
    if lane:
        q = q.filter(lane_id=lane)
    return q.order_by('order')


board = ObjectType('Board')
@board.field('lanes')
def resolve_board_lanes(parent, *_):
    return TaskLane.objects.filter(board_id=parent.id).order_by('order')


taskLane = ObjectType('TaskLane')
taskLane.set_alias('board', 'board_id')
@taskLane.field('tasks')
def resolve_tasklane_board(parent, *_, searchQuery=None):
    q = Task.objects

    if searchQuery:
        if len(searchQuery) < 5:
            raise Exception('search query empty or too short')

        q = q.filter(Q(lane_id=parent.id), Q(title__contains=searchQuery)
                     | Q(description__contains=searchQuery))
    else:
        q = q.filter(lane_id=parent.id)

    return q.order_by('order')


task = ObjectType('Task')
task.set_alias('board', 'board_id')
task.set_alias('lane', 'lane_id')

# @task.field('board')
# def resolve_task_board(parent, *_):
#     return Board.objects.get(id=parent.board_id.id)


# @task.field('lane')
# def resolve_task_board(parent, *_):
#     return TaskLane.objects.get(id=parent.id)


user = ObjectType('User')
@user.field('tasks')
def resolve_user_tasks(parent, *_, board=None, lane=None):
    q = Task.objects.filter(assigned_to=parent.id)

    if board:
        q = q.filter(board_id=board)

    if lane:
        q = q.filter(lane_id=lane)

    return q


schema = make_executable_schema(
    type_defs, query, mutation, board, taskLane, task, user,  snake_case_fallback_resolvers, [date_scalar, datetime_scalar])
