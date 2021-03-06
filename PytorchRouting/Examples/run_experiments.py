"""
This file defines some simple experiments to illustrate how Pytorch-Routing functions.
"""
import numpy as np
import torch
from PytorchRouting.DecisionLayers import REINFORCE, QLearning, SARSA, ActorCritic, GumbelSoftmax, PerTaskAssignment, \
    WPL
from PytorchRouting.Examples.Models import DispatchedRoutedAllFC, RoutedAllFC
from PytorchRouting.Examples.Datasets import CIFAR100MTL


def compute_batch(model, batch):
    samples, labels, tasks = batch
    out, meta = model(samples, tasks=tasks)
    correct_predictions = (out.max(dim=1)[1].squeeze() == labels.squeeze()).cpu().numpy()
    accuracy = correct_predictions.sum()
    oh_labels = one_hot(labels, out.size()[-1])
    module_loss, decision_loss = model.loss(out, oh_labels, meta)
    return module_loss, decision_loss, accuracy

def one_hot(indices, width):
    indices = indices.squeeze().unsqueeze(1)
    oh = torch.zeros(indices.size()[0], width).to(indices.device)
    oh.scatter_(1, indices, 1)
    return oh


def run_experiment(model, dataset, learning_rates):
    print('Loaded dataset and constructed model. Starting Training ...')
    for epoch in range(50):
        optimizers = []
        parameters = []
        if epoch in learning_rates:
            try:
                routing_multiplier = 1.
                optimizers.append(torch.optim.SGD(model.routing_parameters(), lr=routing_multiplier*learning_rates[epoch]))
                optimizers.append(torch.optim.SGD(model.module_parameters(), lr=learning_rates[epoch]))
                parameters = model.module_parameters() + model.module_parameters()
            except AttributeError:
                optimizers.append(torch.optim.SGD(model.parameters(), lr=learning_rates[epoch]))
                parameters = model.parameters()
        train_log, test_log = np.zeros((3,)), np.zeros((3,))
        train_samples_seen, test_samples_seen = 0, 0
        dataset.enter_train_mode()
        model.train()
        while True:
            try:
                batch = dataset.get_batch()
            except StopIteration:
                break
            train_samples_seen += len(batch[0])
            module_loss, decision_loss, accuracy = compute_batch(model, batch)
            (module_loss + decision_loss).backward()
            torch.nn.utils.clip_grad_norm_(parameters, 40., norm_type=2)
            for opt in optimizers:
                opt.step()
            model.zero_grad()
            train_log += np.array([module_loss.tolist(), decision_loss.tolist(), accuracy])
        dataset.enter_test_mode()
        model.eval()
        model.start_logging_selections()
        while True:
            try:
                batch = dataset.get_batch()
            except StopIteration:
                break
            test_samples_seen += len(batch[0])
            module_loss, decision_loss, accuracy = compute_batch(model, batch)
            test_log += np.array([module_loss.tolist(), decision_loss.tolist(), accuracy])
        print('Epoch {} finished after {} train and {} test samples..\n'
              '    Training averages: Model loss: {}, Routing loss: {}, Accuracy: {}\n'
              '    Testing averages:  Model loss: {}, Routing loss: {}, Accuracy: {}'.format(
            epoch + 1, train_samples_seen, test_samples_seen,
            *(train_log/train_samples_seen).round(3), *(test_log/test_samples_seen).round(3)))
        model.stop_logging_selections_and_report()


if __name__ == '__main__':
    # CIFAR
    dataset = CIFAR100MTL(10, data_files=['./Datasets/cifar-100-py/train', './Datasets/cifar-100-py/test'])
    model = RoutedAllFC(WPL, 3, 128, 5, dataset.num_tasks, dataset.num_tasks)
    # model = DispatchedRoutedAllFC(WPL, WPL, 3, 128, 5, dataset.num_tasks, dataset.num_tasks)

    learning_rates = {0: 1e-2, 5: 1e-3, 10: 1e-4}
    model.cuda()
    run_experiment(model, dataset, learning_rates)
